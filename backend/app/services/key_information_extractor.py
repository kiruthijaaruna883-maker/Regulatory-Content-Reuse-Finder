"""Deterministic and AI-assisted key information extraction module.

Extracts structured regulatory entities: dose, frequency, route, population,
drug/active ingredient, product, indication, duration, context, and safety warnings.
"""

import re
from typing import Optional
from app.models.content import KeyInformation


class KeyInformationExtractor:
    """Extracts structured regulatory attributes from text using deterministic clinical rules."""

    # Dosing patterns (e.g. "10 mg", "50 mcg", "250 mg", "1 tablet")
    DOSE_PATTERN = re.compile(
        r"\b(\d+(?:\.\d+)?(?:\s*(?:to|-)\s*\d+(?:\.\d+)?)?)\s*(mg|g|mcg|ml|tablets?|capsules?|drops?|puffs?|units?|mEq)\b",
        re.IGNORECASE,
    )

    # Frequency patterns
    FREQUENCY_PATTERNS = [
        (r"\bonce\s+(?:each\s+day|daily|a\s+day)\b|\bdaily\b|\bq\s*d\b|\bq\.d\.\b", "once daily"),
        (r"\btwice\s+(?:daily|a\s+day|per\s+day)\b|\bb\s*i\s*d\b|\bb\.i\.d\.\b|\bbid\b", "twice daily"),
        (r"\bthree\s+times\s+(?:a|per)\s+day\b|\bt\s*i\s*d\b|\bt\.i\.d\.\b|\btid\b", "three times daily"),
        (r"\bfour\s+times\s+(?:a|per)\s+day\b|\bq\s*i\s*d\b|\bq\.i\.d\.\b|\bqid\b", "four times daily"),
        (r"\bevery\s+(\d+(?:\s*(?:to|-)\s*\d+)?)\s*hours?\b", r"every \1 hours"),
        (r"\bevery\s+morning\b", "every morning"),
        (r"\bat\s+bedtime\b", "at bedtime"),
        (r"\bas\s+needed\b|\bprn\b|\bp\.r\.n\.\b", "as needed"),
        (r"\bq\s*4\s*h\b", "every 4 hours"),
        (r"\bq\s*6\s*h\b", "every 6 hours"),
        (r"\bq\s*8\s*h\b", "every 8 hours"),
        (r"\bq\s*12\s*h\b", "every 12 hours"),
    ]

    # Route patterns
    ROUTE_PATTERNS = [
        (r"\borally\b|\bby\s+mouth\b|\boral\b|\bpo\b|\bp\.o\.\b", "Oral"),
        (r"\bintravenous(?:ly)?\b|\bIV\b|\bi\.v\.\b", "Intravenous"),
        (r"\bsubcutaneous(?:ly)?\b|\bSC\b|\bSubQ\b|\bs\.c\.\b", "Subcutaneous"),
        (r"\bintramuscular(?:ly)?\b|\bIM\b|\bi\.m\.\b", "Intramuscular"),
        (r"\btopical(?:ly)?\b", "Topical"),
        (r"\binhalation\b|\binhaled\b", "Inhalation"),
        (r"\bophthalmic\b", "Ophthalmic"),
        (r"\botic\b", "Otical"),
    ]

    # Population patterns
    POPULATION_PATTERNS = [
        (r"\bpediatric\s+(?:patients?|population)\b|\bchildren\b|\bchild\b|\bpediatrics?\b|\b2\s+to\s+12\s+years\b|\bunder\s+18\s+years\b", "Pediatric patients"),
        (r"\badults?(?:\s+and\s+children\s+12\s+years\s+and\s+over)?\b|\badult\s+(?:patients?|population)\b|\bin\s+adults\b|\b18\s+years\s+(?:of\s+age\s+)?and\s+older\b", "Adults"),
        (r"\bgeriatric\s+(?:patients?|population)\b|\belderly\b|\b65\s+years\s+(?:of\s+age\s+)?and\s+older\b", "Geriatric patients"),
        (r"\bneonates?\b|\bnewborns?\b", "Neonates"),
        (r"\binfants?\b", "Infants"),
    ]

    # Age group patterns
    AGE_PATTERNS = [
        r"\b18\s+years\s+(?:of\s+age\s+)?and\s+older\b",
        r"\b12\s+years\s+(?:of\s+age\s+)?and\s+older\b",
        r"\bunder\s+12\s+years\b",
        r"\bunder\s+18\s+years\b",
        r"\b60\s+years\s+and\s+over\b",
        r"\b65\s+years\s+and\s+over\b",
        r"\b2\s+to\s+11\s+years\b",
        r"\b2\s+to\s+12\s+years\b",
    ]

    # Common pharmaceutical drug stems (USAN/INN stem naming conventions)
    DRUG_STEM_REGEX = re.compile(
        r"\b[A-Za-z]+(?:olol|artan|statin|pril|dipine|prazole|mab|nib|xaban|cillin|mycin|floxacin|zole|triptan|tide|lukast|semide|vir|gliptin|glitazone|afil|dopa|asone|tidine|sone|pam|lam)\b",
        re.IGNORECASE,
    )

    # Expanded dictionary of common generic and branded pharmaceuticals
    KNOWN_DRUGS = [
        "aspirin", "acetylsalicylic acid", "ibuprofen", "acetaminophen", "paracetamol",
        "naproxen", "amoxicillin", "atorvastatin", "metformin", "lisinopril",
        "amlodipine", "omeprazole", "losartan", "gabapentin", "hydrochlorothiazide",
        "sertraline", "simvastatin", "pantoprazole", "furosemide", "prednisone",
        "metoprolol", "albuterol", "levothyroxine", "citalopram", "escitalopram",
        "fluoxetine", "venlafaxine", "duloxetine", "rosuvastatin", "pravastatin",
        "valsartan", "candesartan", "irbesartan", "olmesartan", "ramipril",
        "enalapril", "carvedilol", "atenolol", "propranolol", "bisoprolol",
        "diltiazem", "verapamil", "nifedipine", "spironolactone", "clopidogrel",
        "warfarin", "apixaban", "rivaroxaban", "dabigatran", "heparin",
        "montelukast", "fluticasone", "budesonide", "cetirizine", "loratadine",
        "esomeprazole", "famotidine", "ranitidine", "ondansetron", "sumatriptan",
        "zolmitriptan", "semaglutide", "liraglutide", "dulaglutide", "empagliflozin",
        "dapagliflozin", "sitagliptin", "linagliptin", "tramadol", "codeine",
        "morphine", "oxycodone", "fentanyl", "methadone", "buprenorphine",
        "ciprofloxacin", "levofloxacin", "azithromycin", "doxycycline", "cephalexin",
        "sulfamethoxazole", "trimethoprim", "metronidazole", "fluconazole", "acyclovir",
        "adalimumab", "infliximab", "rituximab", "pembrolizumab", "trastuzumab",
    ]

    def extract(self, text: str) -> KeyInformation:
        """Extract structured KeyInformation from clinical or regulatory text."""
        clean_text = text.strip()
        if not clean_text:
            return KeyInformation()

        info = KeyInformation()
        lower_text = clean_text.lower()

        # 1. Dose and Unit
        dose_match = self.DOSE_PATTERN.search(clean_text)
        if dose_match:
            info.dose = f"{dose_match.group(1)} {dose_match.group(2)}"
            info.dose_unit = dose_match.group(2).lower()

        # 2. Frequency
        for pattern, replacement in self.FREQUENCY_PATTERNS:
            match = re.search(pattern, lower_text)
            if match:
                if "\\" in replacement:
                    info.frequency = match.expand(replacement)
                else:
                    info.frequency = replacement
                break

        # 3. Route
        for pattern, route_label in self.ROUTE_PATTERNS:
            if re.search(pattern, clean_text, re.IGNORECASE):
                info.route = route_label
                break

        # 4. Population
        for pattern, pop_label in self.POPULATION_PATTERNS:
            if re.search(pattern, clean_text, re.IGNORECASE):
                info.population = pop_label
                break

        # 5. Age Group
        for pattern in self.AGE_PATTERNS:
            age_match = re.search(pattern, clean_text, re.IGNORECASE)
            if age_match:
                info.age_group = age_match.group(0).strip()
                break

        # 6. Drug / Active Ingredient Extraction
        # Priority A: Check known generic drug names
        for drug in self.KNOWN_DRUGS:
            if re.search(r"\b" + re.escape(drug) + r"\b", clean_text, re.IGNORECASE):
                info.drug = drug.title()
                info.active_ingredient = drug.title()
                break

        # Priority B: Syntactic patterns (e.g. "50 mg of losartan", "take 50 mg of metoprolol", "atorvastatin 10 mg")
        if not info.drug:
            # Pattern: "X mg of <drug>"
            of_match = re.search(
                r"\b\d+(?:\.\d+)?\s*(?:mg|g|mcg|ml)?\s+of\s+([A-Za-z0-9\-]+)\b",
                clean_text,
                re.IGNORECASE,
            )
            if of_match:
                candidate_drug = of_match.group(1).strip()
                # Exclude non-drug words
                if candidate_drug.lower() not in {"water", "food", "liquid", "solution", "each", "this", "the"}:
                    info.drug = candidate_drug.title()
                    info.active_ingredient = candidate_drug.title()

        if not info.drug:
            # Pattern: "<drug> X mg"
            pre_match = re.search(
                r"\b([A-Za-z0-9\-]{4,25})\s+\d+(?:\.\d+)?\s*(?:mg|g|mcg|ml)\b",
                clean_text,
                re.IGNORECASE,
            )
            if pre_match:
                candidate_drug = pre_match.group(1).strip()
                if candidate_drug.lower() not in {"take", "administer", "receive", "dose", "give", "adults", "initial", "maximum"}:
                    info.drug = candidate_drug.title()
                    info.active_ingredient = candidate_drug.title()

        if not info.drug:
            # Pattern: INN / USAN pharmacological stem matching
            stem_match = self.DRUG_STEM_REGEX.search(clean_text)
            if stem_match:
                info.drug = stem_match.group(0).title()
                info.active_ingredient = stem_match.group(0).title()

        # Priority C: Synthetic / generic product designations (e.g. "Drug A", "Product B")
        synth_match = re.search(r"\b(Drug\s+[A-Z0-9]+|Product\s+[A-Z0-9]+)\b", clean_text, re.IGNORECASE)
        if synth_match:
            detected_name = synth_match.group(1).title()
            if not info.drug:
                info.drug = detected_name
            info.product = detected_name

        # 7. Duration
        duration_match = re.search(
            r"\b(?:for|up to|during)\s+(\d+(?:\s*(?:to|-)\s*\d+)?\s+(?:days?|weeks?|months?|hours?))\b|\b(\d+(?:\s*(?:to|-)\s*\d+)?\s+(?:days?|weeks?|months?))\s+(?:of\s+treatment|course|therapy|duration)\b",
            clean_text,
            re.IGNORECASE,
        )
        if duration_match:
            info.duration = (duration_match.group(1) or duration_match.group(2)).strip()

        # 8. Indication
        ind_match = re.search(
            r"\b(?:indicated for|treatment of|relief of|to relieve|for the management of|management of)\s+([^.,;\n]+)",
            clean_text,
            re.IGNORECASE,
        )
        if ind_match:
            info.indication = ind_match.group(1).strip()
        else:
            # Concise for <indication> pattern
            cond_match = re.search(
                r"\bfor\s+(hypertension|chronic\s+pain(?: management)?|uncomplicated\s+migraine(?: attacks)?|type\s+2\s+diabetes|major\s+depression|asthma)\b",
                clean_text,
                re.IGNORECASE,
            )
            if cond_match:
                info.indication = cond_match.group(1).strip()

        # 9. Safety / Warnings / Contraindications
        safety_match = re.search(
            r"\b(?:contraindicated\s+in|contraindicated|warning[:\s]|do\s+not\s+use\s+if|caution[:\s]|adverse\s+reactions?[:\s]|boxed\s+warning[:\s])\s*([^.,;\n]+)",
            clean_text,
            re.IGNORECASE,
        )
        if safety_match:
            info.safety_information = safety_match.group(1).strip()

        # 10. Regulatory Purpose & Context Classification
        is_study = bool(re.search(r"\b(clinical\s+trials?|patients\s+received|in\s+study\s+\d+|experienced\s+nausea|adverse\s+events?\s+were|placebo)\b", lower_text))
        is_contra = bool(re.search(r"\b(contraindicated|contraindication|do\s+not\s+use|hypersensitivity)\b", lower_text))
        is_indication = bool(re.search(r"\b(indicated\s+for|treatment\s+of|management\s+of|relief\s+of)\b", lower_text)) and not is_contra

        if is_study:
            info.purpose = "Clinical Study Observation"
        elif is_contra:
            info.purpose = "Safety / Contraindication"
        elif is_indication:
            info.purpose = "Therapeutic Indication"
        elif info.dose or info.frequency or "take" in lower_text or "administer" in lower_text:
            info.purpose = "Dosing Specification"
        else:
            info.purpose = "General Prescribing Directive"

        return info


def normalize_route(route: Optional[str]) -> Optional[str]:
    """Conservative canonical normalization for administration route.

    oral, po, by mouth => Oral
    intravenous, iv => Intravenous
    subcutaneous, sc, subq => Subcutaneous
    """
    if not route:
        return None
    r = route.strip().lower().replace(".", "")
    if r in {"oral", "po", "by mouth", "orally"}:
        return "Oral"
    if r in {"intravenous", "iv", "intravenously"}:
        return "Intravenous"
    if r in {"subcutaneous", "sc", "subq", "subcutaneously"}:
        return "Subcutaneous"
    if r in {"intramuscular", "im", "intramuscularly"}:
        return "Intramuscular"
    if r in {"topical", "topically"}:
        return "Topical"
    if r in {"inhalation", "inhaled"}:
        return "Inhalation"
    return route.strip().title()


def normalize_frequency(freq: Optional[str]) -> Optional[str]:
    """Conservative canonical normalization for dosing frequency.

    once daily, daily, qd, q.d. => once daily
    twice daily, bid, b.i.d. => twice daily
    three times daily, tid, t.i.d. => three times daily
    """
    if not freq:
        return None
    f = freq.strip().lower().replace(".", "")
    if f in {"once daily", "daily", "qd", "once a day", "once each day", "every day"}:
        return "once daily"
    if f in {"twice daily", "bid", "twice a day", "per day twice"}:
        return "twice daily"
    if f in {"three times daily", "tid", "three times a day"}:
        return "three times daily"
    if f in {"four times daily", "qid", "four times a day"}:
        return "four times daily"
    return freq.strip().lower()


def normalize_dose_unit(unit: Optional[str]) -> Optional[str]:
    """Canonical normalization for pharmaceutical dose unit."""
    if not unit:
        return None
    u = unit.strip().lower()
    if u in {"mg", "milligram", "milligrams"}:
        return "mg"
    if u in {"mcg", "ug", "microgram", "micrograms"}:
        return "mcg"
    if u in {"g", "gram", "grams"}:
        return "g"
    if u in {"ml", "milliliter", "milliliters"}:
        return "ml"
    if u in {"tablet", "tablets", "tab", "tabs"}:
        return "tablet"
    if u in {"capsule", "capsules", "cap", "caps"}:
        return "capsule"
    return u
