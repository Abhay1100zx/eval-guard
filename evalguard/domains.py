from dataclasses import dataclass
from typing import Dict, Any, Optional

@dataclass
class DomainConfig:
    key: str
    name: str
    description: str
    icon: str
    faithfulness_threshold: float
    relevance_threshold: float
    safeguard_notice: Optional[str]
    sample_question: str

DOMAINS_REGISTRY: Dict[str, DomainConfig] = {
    "education": DomainConfig(
        key="education",
        name="Education",
        description="University academic regulations, enrollment, grading criteria, attendance policies, and campus housing rules.",
        icon="🎓",
        faithfulness_threshold=0.70,
        relevance_threshold=0.70,
        safeguard_notice=None,
        sample_question="What is the minimum attendance percentage required to avoid an attendance warning at the university?"
    ),
    "healthcare": DomainConfig(
        key="healthcare",
        name="Healthcare",
        description="Clinical management guidelines for hypertension, type 2 diabetes, diagnostic thresholds, and routine screenings.",
        icon="🏥",
        faithfulness_threshold=0.80,
        relevance_threshold=0.75,
        safeguard_notice="Medical Safeguard: This evaluation dataset uses synthetic reference guidelines for LLM benchmarking only. Scores do not certify clinical safety or replace licensed medical judgment.",
        sample_question="What is the fasting plasma glucose diagnostic cutoff for Type 2 Diabetes Mellitus?"
    ),
    "banking_finance": DomainConfig(
        key="banking_finance",
        name="Banking and Finance",
        description="Retail banking policies, overdraft limits, wire transfer cutoff times, credit underwriting criteria, and AML regulations.",
        icon="🏦",
        faithfulness_threshold=0.80,
        relevance_threshold=0.75,
        safeguard_notice="Financial Safeguard: Reference policies are synthetic models for benchmark evaluation. Scores do not certify regulatory compliance with FINRA, SEC, or banking authorities.",
        sample_question="What is the daily ATM cash withdrawal limit and overdraft fee structure?"
    ),
    "legal": DomainConfig(
        key="legal",
        name="Legal",
        description="Corporate contracts, Non-Disclosure Agreements (NDAs), intellectual property work-for-hire, arbitration, and GDPR compliance.",
        icon="⚖️",
        faithfulness_threshold=0.80,
        relevance_threshold=0.75,
        safeguard_notice="Legal Safeguard: Benchmark materials are synthetic contract templates for QA testing. Scores do not constitute formal legal counsel or attorney-client verification.",
        sample_question="What is the standard confidentiality duration under the NDA and what are the exclusions?"
    ),
    "ecommerce": DomainConfig(
        key="ecommerce",
        name="E-commerce",
        description="Customer ordering, shipping tiers, return windows, refund processing SLAs, and damaged package policies.",
        icon="🛒",
        faithfulness_threshold=0.70,
        relevance_threshold=0.70,
        safeguard_notice=None,
        sample_question="What is the return window and how long does a refund take to appear on the original payment method?"
    ),
    "it_support": DomainConfig(
        key="it_support",
        name="IT and Technical Support",
        description="API rate limits, OAuth 2.0 token lifecycles, P1-P3 incident SLAs, PostgreSQL connection pooling, and bastion access.",
        icon="💻",
        faithfulness_threshold=0.70,
        relevance_threshold=0.70,
        safeguard_notice=None,
        sample_question="What is the initial response SLA and target resolution time for a Severity 1 (P1) incident?"
    ),
    "hr": DomainConfig(
        key="hr",
        name="Human Resources",
        description="Paid Time Off (PTO) accruals, primary & secondary parental leave, remote work stipends, and PIP guidelines.",
        icon="👥",
        faithfulness_threshold=0.70,
        relevance_threshold=0.70,
        safeguard_notice=None,
        sample_question="How many weeks of fully paid parental leave are provided to primary caregivers?"
    ),
    "travel_hospitality": DomainConfig(
        key="travel_hospitality",
        name="Travel and Hospitality",
        description="Hotel check-in/out policies, flexible cancellation deadlines, pet accommodations, smoking penalties, and flight delay compensation.",
        icon="✈️",
        faithfulness_threshold=0.70,
        relevance_threshold=0.70,
        safeguard_notice=None,
        sample_question="What is the flexible rate cancellation deadline to avoid forfeiting a night's room charge?"
    )
}

# Display name to key mapping
DOMAIN_DISPLAY_NAMES: Dict[str, str] = {
    "Education": "education",
    "Healthcare": "healthcare",
    "Banking and Finance": "banking_finance",
    "Legal": "legal",
    "E-commerce": "ecommerce",
    "IT and Technical Support": "it_support",
    "Human Resources": "hr",
    "Travel and Hospitality": "travel_hospitality"
}

def get_domain_config(domain_key: str) -> DomainConfig:
    key = domain_key.lower().strip()
    if key not in DOMAINS_REGISTRY:
        raise ValueError(f"Unknown domain '{domain_key}'. Supported domains: {list(DOMAINS_REGISTRY.keys())}")
    return DOMAINS_REGISTRY[key]

def get_all_domains() -> Dict[str, DomainConfig]:
    return DOMAINS_REGISTRY
