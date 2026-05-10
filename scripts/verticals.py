#!/usr/bin/env python3
"""Vertical profiles for citation + visibility audits.

Each vertical defines:
  - query_templates: how to ask engines about brands in this vertical
    (generic 'best resources' won't work for a local orthodontist;
    you need 'kid braces in [city]', 'orthodontist near me', etc.)
  - schema_types: which JSON-LD types are weighted in this vertical
    (LocalBusiness/Dentist for healthcare; SoftwareApplication for SaaS;
    Person for personal-brand)
  - indirect_citation_sources: third-party platforms where engines
    might cite the brand even without citing the brand's own site
    (Healthgrades for healthcare; G2/Capterra for SaaS; LinkedIn for
    personal-brand)
  - calibration_anchors: known-high (≥80% brand+topic citation) and
    known-floor (DR <30 in same vertical) reference sites for sanity
    checks
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class VerticalProfile:
    name: str
    description: str
    schema_types: list[str]               # JSON-LD types this vertical weights
    indirect_citation_sources: list[str]  # third-party domains for indirect-citation check
    calibration_anchors: dict[str, str]   # {"high": url, "mid": url, "low": url}
    query_template_builder: Callable[[dict], list[dict]]  # builds queries from context


def _build_local_healthcare_queries(ctx: dict) -> list[dict]:
    """Healthcare + local: queries are geo-aware, service-specific, intent-driven.

    Required ctx keys:
      brand: e.g., "Marston Orthodontics"
      city: e.g., "San Diego"
      neighborhood: e.g., "Rancho Peñasquitos" (optional)
      services: list of services e.g., ["braces", "Invisalign", "clear aligners"]
      patient_segments: e.g., ["kids", "teens", "adults"] (optional)
    """
    brand = ctx["brand"]
    city = ctx.get("city", "")
    neighborhood = ctx.get("neighborhood", city)
    services = ctx.get("services", ["braces"])
    segments = ctx.get("patient_segments", ["adults"])

    queries = []
    qid = 1

    # 5 brand queries — direct brand recognition tests
    for q in [
        f"What is {brand} and what do they do?",
        f"Tell me about {brand} in {city}.",
        f"Is {brand} a good {ctx.get('practice_type', 'orthodontist')} in {city}?",
        f"What services does {brand} offer?",
        f"How long has {brand} been in practice?",
    ]:
        queries.append({"id": qid, "category": "brand", "query": q})
        qid += 1

    # 5 local-intent queries (geo-aware "near me" shape)
    geo_queries = [
        f"Best {ctx.get('practice_type', 'orthodontist')} in {neighborhood}",
        f"Top-rated {ctx.get('practice_type', 'orthodontist')} near {city}",
        f"Where can I get {services[0]} in {city}?",
        f"Affordable {ctx.get('practice_type', 'orthodontist')} in {city}",
        f"{ctx.get('practice_type', 'Orthodontist').capitalize()} accepting new patients in {city}",
    ]
    for q in geo_queries[:5]:
        queries.append({"id": qid, "category": "topic_authority", "query": q})
        qid += 1

    # 5 service-specific long-tail (patient-segment intent)
    long_tail = []
    for service in services[:3]:
        for segment in segments[:2]:
            long_tail.append(f"{service} for {segment} in {city}")
    long_tail = long_tail[:5]
    while len(long_tail) < 5:
        long_tail.append(f"How much does {services[0]} cost in {city}?")
    for q in long_tail[:5]:
        queries.append({"id": qid, "category": "long_tail", "query": q})
        qid += 1

    # 5 competitor / comparison queries
    comp_queries = [
        f"How does {brand} compare to other {ctx.get('practice_type', 'orthodontists')} in {city}?",
        f"Best {ctx.get('practice_type', 'orthodontist')} alternatives to {brand}",
        f"{brand} vs other {ctx.get('practice_type', 'orthodontists')} in {neighborhood}",
        f"Reviews of {brand} compared to other practices",
        f"Why choose {brand} over other {ctx.get('practice_type', 'orthodontists')} in {city}?",
    ]
    for q in comp_queries[:5]:
        queries.append({"id": qid, "category": "competitor", "query": q})
        qid += 1

    return queries


def _build_saas_queries(ctx: dict) -> list[dict]:
    """SaaS-tool vertical: queries focus on category positioning + use-cases."""
    brand = ctx["brand"]
    category = ctx.get("category", "tool")
    use_cases = ctx.get("use_cases", ["productivity"])

    queries = []
    qid = 1

    for q in [
        f"What is {brand} and what does it do?",
        f"How does {brand} work?",
        f"Who built {brand}?",
        f"What problem does {brand} solve?",
        f"Tell me about {brand} as a {category}.",
    ]:
        queries.append({"id": qid, "category": "brand", "query": q})
        qid += 1

    for uc in use_cases[:5]:
        queries.append({"id": qid, "category": "topic_authority", "query": f"What's the best {category} for {uc}?"})
        qid += 1
    while len([q for q in queries if q["category"] == "topic_authority"]) < 5:
        queries.append({"id": qid, "category": "topic_authority", "query": f"What's the best {category} in 2026?"})
        qid += 1

    for uc in use_cases[:5]:
        queries.append({"id": qid, "category": "long_tail", "query": f"How do I get started with {category} for {uc}?"})
        qid += 1
    while len([q for q in queries if q["category"] == "long_tail"]) < 5:
        queries.append({"id": qid, "category": "long_tail", "query": f"How do I evaluate a {category}?"})
        qid += 1

    for uc in use_cases[:5]:
        queries.append({"id": qid, "category": "competitor", "query": f"How does {brand} compare to other {category}s for {uc}?"})
        qid += 1
    while len([q for q in queries if q["category"] == "competitor"]) < 5:
        queries.append({"id": qid, "category": "competitor", "query": f"What are alternatives to {brand}?"})
        qid += 1

    return queries


def _build_personal_brand_queries(ctx: dict) -> list[dict]:
    """Personal-brand vertical: queries focus on the person's expertise + body of work."""
    brand = ctx["brand"]  # the person's name
    expertise = ctx.get("expertise", ["AI engineering"])

    queries = []
    qid = 1

    for q in [
        f"Who is {brand}?",
        f"What is {brand} known for?",
        f"What does {brand} write about?",
        f"What projects has {brand} built?",
        f"Tell me about {brand}'s work.",
    ]:
        queries.append({"id": qid, "category": "brand", "query": q})
        qid += 1

    for exp in expertise[:5]:
        queries.append({"id": qid, "category": "topic_authority", "query": f"Who are the experts on {exp}?"})
        qid += 1
    while len([q for q in queries if q["category"] == "topic_authority"]) < 5:
        queries.append({"id": qid, "category": "topic_authority", "query": f"Who writes about {expertise[0]}?"})
        qid += 1

    for exp in expertise[:5]:
        queries.append({"id": qid, "category": "long_tail", "query": f"How do I learn {exp} from practitioners?"})
        qid += 1
    while len([q for q in queries if q["category"] == "long_tail"]) < 5:
        queries.append({"id": qid, "category": "long_tail", "query": f"Best resources for learning {expertise[0]}?"})
        qid += 1

    for exp in expertise[:5]:
        queries.append({"id": qid, "category": "competitor", "query": f"How does {brand} compare to other writers on {exp}?"})
        qid += 1
    while len([q for q in queries if q["category"] == "competitor"]) < 5:
        queries.append({"id": qid, "category": "competitor", "query": f"Who are alternatives to {brand} for {expertise[0]}?"})
        qid += 1

    return queries


# === Registry of vertical profiles ===

VERTICALS = {
    "local-healthcare": VerticalProfile(
        name="local-healthcare",
        description="Local healthcare practice (dentist, orthodontist, physical therapist, doctor's office, etc.)",
        schema_types=[
            "LocalBusiness",
            "MedicalBusiness",
            "Dentist",
            "Physician",
            "MedicalProcedure",
            "Place",
            "PostalAddress",
            "GeoCoordinates",
        ],
        indirect_citation_sources=[
            "healthgrades.com",
            "yelp.com",
            "google.com/maps",
            "vitals.com",
            "realself.com",  # cosmetic-procedure focused
            "zocdoc.com",
            "yourabms.org",  # ABMS board-cert verification
            "aaoinfo.org",   # AAO orthodontist directory
            "ada.org",       # ADA dentist directory
            "bbb.org",
        ],
        calibration_anchors={
            "high": "https://www.mayoclinic.org",
            "mid": "https://www.ada.org",
            "low": "https://drsmith-dental.example.com",  # placeholder; operator picks a real DR<30 local practice
        },
        query_template_builder=_build_local_healthcare_queries,
    ),
    "saas-tool": VerticalProfile(
        name="saas-tool",
        description="SaaS / developer tool / productivity software",
        schema_types=[
            "SoftwareApplication",
            "WebApplication",
            "Product",
            "Organization",
            "Offer",
            "AggregateRating",
        ],
        indirect_citation_sources=[
            "g2.com",
            "capterra.com",
            "producthunt.com",
            "github.com",
            "trustpilot.com",
            "saasworthy.com",
            "alternativeto.net",
        ],
        calibration_anchors={
            "high": "https://stripe.com",
            "mid": "https://vercel.com",
            "low": "https://citability.dev",  # known floor (own product)
        },
        query_template_builder=_build_saas_queries,
    ),
    "personal-brand": VerticalProfile(
        name="personal-brand",
        description="Individual practitioner, consultant, writer, indie creator's personal site",
        schema_types=[
            "Person",
            "ProfilePage",
            "Article",
            "Blog",
            "BlogPosting",
            "Organization",
        ],
        indirect_citation_sources=[
            "linkedin.com",
            "twitter.com",
            "x.com",
            "github.com",
            "medium.com",
            "substack.com",
            "youtube.com",
            "wikipedia.org",
        ],
        calibration_anchors={
            "high": "https://patrickcollison.com",
            "mid": "https://danluu.com",
            "low": "https://chudi.dev",  # known floor (own site)
        },
        query_template_builder=_build_personal_brand_queries,
    ),
    "tech-publisher": VerticalProfile(
        name="tech-publisher",
        description="Tutorial site, learning platform, publisher (freeCodeCamp, MDN, Codecademy, Dev.to)",
        schema_types=[
            "Organization",
            "Course",
            "LearningResource",
            "Article",
            "TechArticle",
            "WebSite",
        ],
        indirect_citation_sources=[
            "github.com",
            "stackoverflow.com",
            "dev.to",
            "medium.com",
            "wikipedia.org",
            "youtube.com",
        ],
        calibration_anchors={
            "high": "https://developer.mozilla.org",
            "mid": "https://www.freecodecamp.org",
            "low": "https://chudi.dev",
        },
        query_template_builder=lambda ctx: [],  # use the default citation_auto.py templates
    ),
}


def get_vertical(name: str) -> VerticalProfile:
    if name not in VERTICALS:
        raise ValueError(f"Unknown vertical: {name}. Available: {list(VERTICALS.keys())}")
    return VERTICALS[name]


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        v = get_vertical(sys.argv[1])
        print(f"Vertical: {v.name}")
        print(f"Description: {v.description}")
        print(f"Schema types ({len(v.schema_types)}): {v.schema_types}")
        print(f"Indirect-citation sources ({len(v.indirect_citation_sources)}): {v.indirect_citation_sources}")
        print(f"Calibration anchors: {v.calibration_anchors}")
        if sys.argv[1] == "local-healthcare":
            ctx = {
                "brand": "Marston Orthodontics",
                "city": "San Diego",
                "neighborhood": "Rancho Peñasquitos",
                "services": ["braces", "Invisalign", "clear aligners"],
                "patient_segments": ["kids", "teens", "adults"],
                "practice_type": "orthodontist",
            }
            queries = v.query_template_builder(ctx)
            print(f"\nGenerated {len(queries)} queries for Marston:")
            for q in queries:
                print(f"  [{q['id']:2}] {q['category']:18s} {q['query']}")
    else:
        print("Available verticals:", list(VERTICALS.keys()))
