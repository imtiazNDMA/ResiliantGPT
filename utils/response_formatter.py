"""
Intelligent Response Classification and Formatting for ResilienceGPT
"""

import re
import json
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum
from dataclasses import dataclass
from langchain_core.prompts import PromptTemplate


class ResponseType(Enum):
    """Classification of different response types based on content and intent"""

    FACTUAL = "factual"  # Direct facts, definitions, explanations
    PROCEDURAL = "procedural"  # Step-by-step processes, guidelines, protocols
    CONCEPTUAL = "conceptual"  # Theories, frameworks, principles
    ANALYTICAL = "analytical"  # Risk assessment, evaluation, comparison
    ACTIONABLE = "actionable"  # Immediate actions, recommendations, alerts
    TECHNICAL = "technical"  # Formulas, calculations, specifications
    REGULATORY = "regulatory"  # Laws, policies, compliance requirements
    EDUCATIONAL = "educational"  # Training, awareness, capacity building
    PREDICTIVE = "predictive"  # Forecasting, scenario planning, trends


@dataclass
class CriticalInformation:
    """Structured representation of critical information extracted from text"""

    concepts: Optional[List[str]] = None
    formulas: Optional[List[Dict[str, str]]] = None
    laws_and_policies: Optional[List[Dict[str, str]]] = None
    procedures: Optional[List[Dict[str, str]]] = None
    key_findings: Optional[List[str]] = None
    recommendations: Optional[List[str]] = None
    warnings: Optional[List[str]] = None
    definitions: Optional[Dict[str, str]] = None

    def __post_init__(self):
        if self.concepts is None:
            self.concepts = []
        if self.formulas is None:
            self.formulas = []
        if self.laws_and_policies is None:
            self.laws_and_policies = []
        if self.procedures is None:
            self.procedures = []
        if self.key_findings is None:
            self.key_findings = []
        if self.recommendations is None:
            self.recommendations = []
        if self.warnings is None:
            self.warnings = []
        if self.definitions is None:
            self.definitions = {}


class ResponseClassifier:
    """Intelligent classifier for determining response type and extracting critical information"""

    def __init__(self):
        self.classification_prompt = PromptTemplate.from_template("""
        Analyze the user's question and retrieved context to classify the appropriate response type.

        ### User Question:
        {query}

        ### Retrieved Context:
        {context}

        ### Response Type Classification:
        Choose the most appropriate response type from:
        - FACTUAL: Direct facts, definitions, explanations, historical data
        - PROCEDURAL: Step-by-step processes, guidelines, protocols, checklists
        - CONCEPTUAL: Theories, frameworks, principles, conceptual models
        - ANALYTICAL: Risk assessment, evaluation, comparison, impact analysis
        - ACTIONABLE: Immediate actions, recommendations, alerts, emergency response
        - TECHNICAL: Formulas, calculations, specifications, technical standards
        - REGULATORY: Laws, policies, compliance requirements, legal frameworks
        - EDUCATIONAL: Training, awareness, capacity building, best practices
        - PREDICTIVE: Forecasting, scenario planning, trends, projections

        ### Critical Information Extraction:
        Extract and structure the following from the context:
        1. Key Concepts: Core ideas, principles, or frameworks
        2. Formulas/Equations: Mathematical formulas, calculations, or algorithms
        3. Laws/Policies: Legal requirements, regulations, or policy frameworks
        4. Procedures: Step-by-step processes or protocols
        5. Key Findings: Important research findings or conclusions
        6. Recommendations: Actionable recommendations or guidelines
        7. Warnings: Critical alerts, risks, or cautions
        8. Definitions: Important term definitions

        ### Output Format (JSON):
        {{
            "response_type": "TYPE_NAME",
            "confidence": 0.0-1.0,
            "critical_info": {{
                "concepts": ["concept1", "concept2"],
                "formulas": [{{"name": "formula_name", "expression": "formula", "description": "what it calculates"}}],
                "laws_and_policies": [{{"name": "law_name", "description": "law description", "reference": "ref"}}],
                "procedures": [{{"name": "procedure_name", "steps": ["step1", "step2"], "purpose": "purpose"}}],
                "key_findings": ["finding1", "finding2"],
                "recommendations": ["recommendation1", "recommendation2"],
                "warnings": ["warning1", "warning2"],
                "definitions": {{"term": "definition", "term2": "definition2"}}
            }},
            "response_structure": "Brief description of how to structure the response"
        }}

        ### Analysis:
        """)

    def classify_and_extract(
        self, query: str, context: str, llm_client
    ) -> Tuple[ResponseType, CriticalInformation, str]:
        """
        Classify response type and extract critical information

        Args:
            query: User's question
            context: Retrieved context chunks
            llm_client: LLM client for classification

        Returns:
            Tuple of (response_type, critical_info, response_structure)
        """
        try:
            # Get classification and extraction from LLM
            chain = self.classification_prompt | llm_client
            result = chain.invoke(
                {
                    "query": query,
                    "context": context[:4000],  # Limit context length
                }
            )

            # Parse JSON response
            analysis = json.loads(result.content.strip())

            # Extract response type
            response_type = ResponseType(
                analysis.get("response_type", "FACTUAL").lower()
            )

            # Extract critical information
            critical_info_data = analysis.get("critical_info", {})
            critical_info = CriticalInformation(
                concepts=critical_info_data.get("concepts", []),
                formulas=critical_info_data.get("formulas", []),
                laws_and_policies=critical_info_data.get("laws_and_policies", []),
                procedures=critical_info_data.get("procedures", []),
                key_findings=critical_info_data.get("key_findings", []),
                recommendations=critical_info_data.get("recommendations", []),
                warnings=critical_info_data.get("warnings", []),
                definitions=critical_info_data.get("definitions", {}),
            )

            response_structure = analysis.get(
                "response_structure", "Provide a comprehensive response"
            )

            return response_type, critical_info, response_structure

        except Exception as e:
            # Fallback to basic classification
            print(f"Classification failed: {e}")
            return (
                ResponseType.FACTUAL,
                CriticalInformation(),
                "Provide a factual response",
            )


class ResponseFormatter:
    """Professional response formatter with structured output"""

    def __init__(self):
        # We can keep the map if we want specific logic later, but for now we use a unified natural approach
        pass

    def format_response(
        self,
        response_type: ResponseType,
        critical_info: CriticalInformation,
        base_response: str,
        references: List[Dict],
    ) -> str:
        """
        Format the final response based on type and critical information
        
        Args:
            response_type: Classified response type
            critical_info: Extracted critical information
            base_response: Base LLM response
            references: List of references

        Returns:
            Formatted professional response
        """
        # Validate and filter references
        validated_references = self._validate_references(references)
        
        response_parts = []

        # 1. Warnings (Always keep these prominent for safety)
        if critical_info.warnings:
            for warning in critical_info.warnings:
                response_parts.append(f"> [!WARNING]\n> {warning}")
            response_parts.append("")

        # 2. Base Response (The natural conversational part)
        response_parts.append(base_response)
        
        # 3. References (Subtle, at the end)
        if validated_references:
            response_parts.append("")
            response_parts.append("---") 
            response_parts.append("### Sources")
            formatted_refs = self._format_reference_list(validated_references)
            response_parts.extend(formatted_refs)

        return "\n".join(response_parts)

    def _validate_references(self, references: List[Dict]) -> List[Dict]:
        """
        Validate references to ensure they contain actual citation information
        and are not hallucinated or empty.

        Args:
            references: Raw list of references from vector search

        Returns:
            Filtered list of valid references only
        """
        if not references:
            return []

        validated_refs = []

        for ref in references:
            # Check if reference has minimum required information
            citation_id = ref.get("citation_id", "").strip()
            title = ref.get("title", "").strip()
            authors = ref.get("authors", "").strip()
            raw_reference = ref.get("raw_reference", "").strip()

            # Must have either a citation ID or meaningful content
            has_citation_id = bool(citation_id)
            has_title = bool(title and len(title) > 3)  # Title must be meaningful
            has_authors = bool(
                authors and len(authors) > 2
            )  # Authors must be meaningful
            has_raw_reference = bool(
                raw_reference and len(raw_reference) > 10
            )  # Raw reference must be substantial

            # Accept reference if it has citation ID OR (title/authors AND raw reference)
            if has_citation_id or (has_raw_reference and (has_title or has_authors)):
                # Clean up the reference data
                cleaned_ref = {
                    "citation_id": citation_id,
                    "title": title,
                    "authors": authors,
                    "year": ref.get("year", "").strip(),
                    "raw_reference": raw_reference,
                }
                validated_refs.append(cleaned_ref)

        return validated_refs

    def _format_reference_list(self, references: List[Dict]) -> List[str]:
        """Format a list of references for display"""
        if not references:
            return []

        formatted_refs = []
        for i, ref in enumerate(references, 1):
            # Format reference properly based on available information
            citation_id = ref.get("citation_id", "").strip()
            title = ref.get("title", "").strip()
            authors = ref.get("authors", "").strip()
            year = ref.get("year", "").strip()

            # Build reference string with available information
            ref_parts = []
            if citation_id:
                ref_parts.append(f"**[{citation_id}]**")
            if authors:
                ref_parts.append(authors)
            if title:
                ref_parts.append(f"_{title}_")
            if year:
                ref_parts.append(f"({year})")

            if ref_parts:
                ref_string = " ".join(ref_parts)
                formatted_refs.append(f"- {ref_string}")
            else:
                # Fallback to raw reference if structured data is missing
                raw_ref = ref.get("raw_reference", "").strip()
                if raw_ref and len(raw_ref) > 10:
                    # Truncate very long references for readability
                    truncated_ref = (
                        raw_ref[:200] + "..." if len(raw_ref) > 200 else raw_ref
                    )
                    formatted_refs.append(f"- {truncated_ref}")

        return formatted_refs
