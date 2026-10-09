"""Live regulatory sources service module.

Integrates with public live regulatory APIs:
- NLM DailyMed Web Services V2 (SPLs, live XML extraction)
- FDA / openFDA Drug Labeling API

CRITICAL: Does NOT download or bundle full regulatory datasets.
All retrieval occurs on-demand via external live web services.
Full source provenance, identifiers, and traceability are strictly preserved.
"""

import logging
import re
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import httpx
from app.config import settings
from app.models.content import RegulatoryContentItem, RegulatorySearchResult

logger = logging.getLogger("regulatory_source")


class BaseRegulatorySource(ABC):
    """Abstract interface for external live regulatory sources."""

    @abstractmethod
    async def search(
        self,
        query: str,
        section: Optional[str] = None,
        limit: int = 10,
    ) -> List[RegulatoryContentItem]:
        """Search the live source for regulatory content items matching the query."""
        pass

    @abstractmethod
    async def get_document_details(
        self,
        identifier: str,
    ) -> List[RegulatoryContentItem]:
        """Fetch detailed sections for a specific regulatory document identifier."""
        pass

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Verify live connectivity to the regulatory source service."""
        pass


class DailyMedSource(BaseRegulatorySource):
    """Live integration with National Library of Medicine (NLM) DailyMed Web Services V2.

    Fetches live Structured Product Labeling (SPL) metadata and section contents on demand.
    Never bundles or downloads the full DailyMed corpus.
    """

    def __init__(self, base_url: Optional[str] = None, timeout: Optional[float] = None):
        self.base_url = base_url or settings.DAILYMED_BASE_URL
        self.timeout = timeout or settings.REQUEST_TIMEOUT_SECONDS

    async def search(
        self,
        query: str,
        section: Optional[str] = None,
        limit: int = 10,
    ) -> List[RegulatoryContentItem]:
        """Execute a live search against DailyMed SPL services.

        Args:
            query: Drug name or active substance to query.
            section: Optional section filter.
            limit: Maximum results to retrieve (1 to 50).
        """
        clean_query = query.strip()
        if not clean_query:
            return []

        search_url = f"{self.base_url}/spls.json"
        params = {
            "drug_name": clean_query,
            "pagesize": min(limit, 50),
        }

        items: List[RegulatoryContentItem] = []

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(search_url, params=params)

                if response.status_code != 200:
                    logger.warning(
                        "DailyMed SPL search returned status %s for query %s",
                        response.status_code,
                        clean_query,
                    )
                    return []

                payload = response.json()
                data_list = payload.get("data", [])

                for record in data_list:
                    setid = record.get("setid")
                    title = record.get("title") or "DailyMed Drug Label"
                    spl_version = str(record.get("spl_version") or "1")
                    published_date = record.get("published_date")

                    # Extract primary drug name from title if possible
                    drug_match = re.search(r"\(([^)]+)\)", title)
                    drug_name = drug_match.group(1) if drug_match else clean_query

                    item = RegulatoryContentItem(
                        document_id=setid,
                        document_name=title,
                        source="DailyMed",
                        source_url=f"https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid={setid}" if setid else None,
                        source_identifier=setid,
                        version=spl_version,
                        date=published_date,
                        section=section or "General Labeling",
                        drug=drug_name,
                        product=title.split("(")[0].strip() if "(" in title else title,
                        content_type="FDA Approved SPL Labeling",
                        text=f"Structured Product Labeling (SPL) for {title}. Set ID: {setid}, Published: {published_date}.",
                        metadata={
                            "dailymed_setid": setid,
                            "published_date": published_date,
                            "spl_version": spl_version,
                        },
                    )
                    items.append(item)

                # Attempt XML section hydration for top SPL record(s) if available
                for top_item in items[:2]:
                    setid_to_fetch = top_item.document_id
                    if setid_to_fetch:
                        try:
                            detail_sections = await self.get_document_details(setid_to_fetch)
                            if detail_sections:
                                sec_clean = (section or "").lower().strip()
                                matching_secs = [
                                    s for s in detail_sections
                                    if sec_clean and (sec_clean in (s.section or "").lower() or (s.section or "").lower() in sec_clean)
                                ]
                                chosen_sec = matching_secs[0] if matching_secs else detail_sections[0]
                                if chosen_sec.text and len(chosen_sec.text.strip()) > 30:
                                    top_item.text = chosen_sec.text
                                    top_item.section = chosen_sec.section or top_item.section
                                    if chosen_sec.location:
                                        top_item.location = chosen_sec.location
                        except Exception as hydrate_err:
                            logger.debug("DailyMed section hydration skipped for %s: %s", setid_to_fetch, hydrate_err)

        except httpx.TimeoutException:
            logger.error("DailyMed search timed out after %s seconds for query: %s", self.timeout, clean_query)
            raise TimeoutError(f"DailyMed live service timed out after {self.timeout}s")
        except httpx.RequestError as exc:
            logger.error("DailyMed connection error for query %s: %s", clean_query, exc)
            raise ConnectionError(f"DailyMed live service unavailable: {exc}")
        except Exception as exc:
            logger.error("Unexpected error parsing DailyMed response: %s", exc)
            raise ValueError(f"Failed to process DailyMed response: {exc}")

        return items

    async def get_document_details(self, identifier: str) -> List[RegulatoryContentItem]:
        """Fetch and parse live SPL XML sections for a specific DailyMed Set ID."""
        setid = identifier.strip()
        xml_url = f"{self.base_url}/spls/{setid}.xml"
        items: List[RegulatoryContentItem] = []

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(xml_url)

                if response.status_code != 200:
                    logger.warning("DailyMed XML fetch failed for setid %s with status %s", setid, response.status_code)
                    return []

                xml_text = response.text
                items = self._parse_spl_xml(xml_text, setid)

        except Exception as exc:
            logger.error("Failed to fetch/parse DailyMed XML for setid %s: %s", setid, exc)
            # Safe degradation: do not crash, return empty list or rethrow if connection issue
            if isinstance(exc, (httpx.TimeoutException, httpx.RequestError)):
                raise ConnectionError(f"DailyMed XML service unavailable: {exc}")

        return items

    def _parse_spl_xml(self, xml_content: str, setid: str) -> List[RegulatoryContentItem]:
        """Parse HL7 SPL XML into structured section items without inventing fields."""
        items: List[RegulatoryContentItem] = []
        try:
            # Strip XML namespaces for standard parsing
            xml_clean = re.sub(r' xmlns="[^"]+"', "", xml_content, count=1)
            root = ET.fromstring(xml_clean)

            # Extract document title
            doc_title = "DailyMed Label"
            title_el = root.find(".//title")
            if title_el is not None and title_el.text:
                doc_title = title_el.text.strip()

            # Iterate through structured sections
            for section in root.iter("section"):
                code_el = section.find("code")
                title_node = section.find("title")
                section_title = None
                loinc_code = None

                if code_el is not None:
                    section_title = code_el.attrib.get("displayName")
                    loinc_code = code_el.attrib.get("code")

                if not section_title and title_node is not None:
                    section_title = "".join(title_node.itertext()).strip()

                if not section_title:
                    continue

                # Extract text paragraphs
                text_node = section.find("text")
                body_text = ""
                if text_node is not None:
                    body_text = " ".join("".join(p.itertext()).strip() for p in text_node.iter("paragraph") if "".join(p.itertext()).strip())
                    if not body_text:
                        body_text = "".join(text_node.itertext()).strip()

                if not body_text or len(body_text) < 15:
                    continue

                item = RegulatoryContentItem(
                    document_id=setid,
                    document_name=doc_title,
                    source="DailyMed",
                    source_url=f"https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid={setid}",
                    source_identifier=setid,
                    section=section_title,
                    location=loinc_code,
                    text=body_text[:4000],  # Bound length for memory safety
                    metadata={
                        "loinc_code": loinc_code,
                        "dailymed_setid": setid,
                    },
                )
                items.append(item)

        except Exception as exc:
            logger.warning("Error parsing SPL XML for setid %s: %s", setid, exc)

        return items

    async def health_check(self) -> Dict[str, Any]:
        """Check live DailyMed API availability."""
        test_url = f"{self.base_url}/drugnames.json"
        try:
            async with httpx.AsyncClient(timeout=min(self.timeout, 5.0)) as client:
                res = await client.get(test_url, params={"pagesize": 1})
                return {
                    "source": "DailyMed",
                    "status": "healthy" if res.status_code == 200 else "degraded",
                    "status_code": res.status_code,
                    "endpoint": test_url,
                }
        except Exception as exc:
            return {
                "source": "DailyMed",
                "status": "unreachable",
                "error": str(exc),
                "endpoint": test_url,
            }


class OpenFDASource(BaseRegulatorySource):
    """Live integration with official FDA / openFDA Drug Labeling API.

    Queries openFDA live on demand. Preserves FDA product labels, NDC, and section texts.
    """

    # Mapping of standard openFDA label section keys to human-readable titles
    SECTION_MAPPINGS = {
        "indications_and_usage": "Indications and Usage",
        "dosage_and_administration": "Dosage and Administration",
        "warnings": "Warnings",
        "warnings_and_cautions": "Warnings and Cautions",
        "contraindications": "Contraindications",
        "adverse_reactions": "Adverse Reactions",
        "drug_interactions": "Drug Interactions",
        "use_in_specific_populations": "Use in Specific Populations",
        "overdosage": "Overdosage",
        "description": "Description",
        "clinical_pharmacology": "Clinical Pharmacology",
    }

    def __init__(self, base_url: Optional[str] = None, timeout: Optional[float] = None):
        self.base_url = base_url or settings.OPENFDA_BASE_URL
        self.timeout = timeout or settings.REQUEST_TIMEOUT_SECONDS
        self.api_key = settings.OPENFDA_API_KEY

    async def search(
        self,
        query: str,
        section: Optional[str] = None,
        limit: int = 10,
    ) -> List[RegulatoryContentItem]:
        """Search openFDA live drug label repository.

        Handles 404 (no matches found) as empty results.
        """
        clean_query = query.strip()
        if not clean_query:
            return []

        # Construct openFDA query targeting brand name, generic name, or substance
        # Escaping quotes to prevent malformed query syntax
        sanitized_q = clean_query.replace('"', "")
        is_heading_query = bool(re.search(r"^(section\s*\d+|part\s*\d+|indications?(\s+and\s+usage)?|dosage(\s+and\s+administration)?|contraindications?|warnings?|precautions?|storage)", sanitized_q, re.I))
        if is_heading_query:
            search_param = sanitized_q
        else:
            search_param = f'openfda.brand_name:"{sanitized_q}"+openfda.generic_name:"{sanitized_q}"'

        params: Dict[str, Any] = {
            "search": search_param,
            "limit": min(limit, 20),
        }
        if self.api_key:
            params["api_key"] = self.api_key

        items: List[RegulatoryContentItem] = []

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.base_url, params=params)

                # openFDA returns 404 with {"error": {"code": "NOT_FOUND"}} when no records match
                if response.status_code == 404:
                    # Fall back to general full-text search across labels
                    params["search"] = sanitized_q
                    response = await client.get(self.base_url, params=params)
                    if response.status_code == 404:
                        return []

                if response.status_code != 200:
                    logger.warning("openFDA search returned status %s for query %s", response.status_code, clean_query)
                    return []

                payload = response.json()
                results = payload.get("results", [])

                for doc in results:
                    openfda_meta = doc.get("openfda", {})
                    doc_id = doc.get("id") or doc.get("set_id")
                    brand_names = openfda_meta.get("brand_name", [])
                    generic_names = openfda_meta.get("generic_name", [])
                    product_name = brand_names[0] if brand_names else (generic_names[0] if generic_names else "Drug Label")
                    drug_name = generic_names[0] if generic_names else clean_query
                    effective_date = doc.get("effective_time")
                    version = doc.get("version")

                    # Extract primary sections
                    for key, display_title in self.SECTION_MAPPINGS.items():
                        if section and section.lower() not in display_title.lower() and section.lower() not in key:
                            continue

                        sec_content = doc.get(key)
                        if sec_content and isinstance(sec_content, list) and len(sec_content) > 0:
                            text_body = " ".join(sec_content).strip()
                            if not text_body:
                                continue

                            item = RegulatoryContentItem(
                                document_id=doc_id,
                                document_name=f"{product_name} - FDA Label",
                                source="openFDA",
                                source_url=f"https://labels.fda.gov/" if doc_id else None,
                                source_identifier=doc_id,
                                version=str(version) if version else None,
                                date=effective_date,
                                section=display_title,
                                product=product_name,
                                drug=drug_name,
                                content_type="FDA Drug Label",
                                text=text_body[:4000],
                                metadata={
                                    "openfda_id": doc_id,
                                    "application_number": openfda_meta.get("application_number", [None])[0],
                                    "manufacturer_name": openfda_meta.get("manufacturer_name", [None])[0],
                                    "route": openfda_meta.get("route", [None])[0],
                                },
                            )
                            items.append(item)

        except httpx.TimeoutException:
            logger.error("openFDA search timed out after %s seconds for query %s", self.timeout, clean_query)
            raise TimeoutError(f"openFDA live service timed out after {self.timeout}s")
        except httpx.RequestError as exc:
            logger.error("openFDA connection error for query %s: %s", clean_query, exc)
            raise ConnectionError(f"openFDA live service unavailable: {exc}")
        except Exception as exc:
            logger.error("Unexpected error in openFDA search: %s", exc)
            raise ValueError(f"Failed to process openFDA response: {exc}")

        return items

    async def get_document_details(self, identifier: str) -> List[RegulatoryContentItem]:
        """Retrieve openFDA label details by document identifier."""
        clean_id = identifier.strip()
        params: Dict[str, Any] = {"search": f'id:"{clean_id}"', "limit": 1}
        if self.api_key:
            params["api_key"] = self.api_key

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.base_url, params=params)
                if response.status_code == 200:
                    payload = response.json()
                    results = payload.get("results", [])
                    if results:
                        # Re-use parsing logic
                        doc = results[0]
                        # Return items for all available sections in this doc
                        return await self.search(doc.get("openfda", {}).get("brand_name", [""])[0] or identifier, limit=5)
        except Exception as exc:
            logger.warning("Error fetching openFDA document %s: %s", clean_id, exc)

        return []

    async def health_check(self) -> Dict[str, Any]:
        """Check live openFDA API availability."""
        try:
            async with httpx.AsyncClient(timeout=min(self.timeout, 5.0)) as client:
                res = await client.get(self.base_url, params={"limit": 1})
                return {
                    "source": "openFDA",
                    "status": "healthy" if res.status_code == 200 else "degraded",
                    "status_code": res.status_code,
                    "endpoint": self.base_url,
                }
        except Exception as exc:
            return {
                "source": "openFDA",
                "status": "unreachable",
                "error": str(exc),
                "endpoint": self.base_url,
            }


class RegulatorySourceService:
    """Unified service orchestrating queries across all configured live regulatory sources."""

    def __init__(
        self,
        dailymed_source: Optional[DailyMedSource] = None,
        openfda_source: Optional[OpenFDASource] = None,
    ):
        self.dailymed = dailymed_source or DailyMedSource()
        self.openfda = openfda_source or OpenFDASource()

    async def search(
        self,
        query: str,
        source: str = "all",
        section: Optional[str] = None,
        limit: int = 10,
    ) -> RegulatorySearchResult:
        """Query live sources and return unified, structured, and traceable regulatory content.

        Args:
            query: Search query (drug name, indication, product).
            source: 'all', 'dailymed', or 'openfda'.
            section: Optional section filter.
            limit: Maximum items per source.
        """
        source_normalized = source.lower().strip()
        all_items: List[RegulatoryContentItem] = []
        errors: List[str] = []

        # Query DailyMed if requested
        if source_normalized in ("all", "dailymed"):
            try:
                dm_items = await self.dailymed.search(query=query, section=section, limit=limit)
                all_items.extend(dm_items)
            except Exception as exc:
                err_msg = f"DailyMed live service warning: {exc}"
                logger.warning(err_msg)
                errors.append(err_msg)

        # Query openFDA if requested
        if source_normalized in ("all", "openfda"):
            try:
                fda_items = await self.openfda.search(query=query, section=section, limit=limit)
                all_items.extend(fda_items)
            except Exception as exc:
                err_msg = f"openFDA live service warning: {exc}"
                logger.warning(err_msg)
                errors.append(err_msg)

        return RegulatorySearchResult(
            query=query,
            total_results=len(all_items),
            source=source,
            items=all_items,
            errors=errors if errors else None,
        )

    async def check_all_sources_health(self) -> Dict[str, Any]:
        """Check live connectivity across all registered regulatory sources."""
        dm_health = await self.dailymed.health_check()
        fda_health = await self.openfda.health_check()

        all_healthy = dm_health.get("status") == "healthy" and fda_health.get("status") == "healthy"

        return {
            "overall_status": "healthy" if all_healthy else "degraded",
            "sources": {
                "dailymed": dm_health,
                "openfda": fda_health,
            },
        }
