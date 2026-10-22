"""Flat Gemini wire fields; strict local contracts check structure and evidence.

No JSON is embedded inside a string. Mapping changes field layout only and
never supplies missing model content, observation IDs, figures or quotations.
"""
from pydantic import BaseModel, ConfigDict


class GeminiBriefingFields(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, revalidate_instances="always")
    executive_observation_id: str
    executive_interpretation: str
    executive_passage_ids: list[str]
    primary_interpretation: str
    primary_passage_ids: list[str]
    primary_alternative_explanation: str
    primary_limitations: list[str]
    additional_observation_id: str
    additional_interpretation: str
    additional_passage_ids: list[str]
    additional_alternative_explanation: str
    additional_limitations: list[str]
    risk_interpretation: str
    risk_passage_ids: list[str]
    risk_limitations: list[str]
    unanswered_questions: list[str]

    def compact_payload(self):
        return {
            "executive_interpretation": {"observation_ids": [self.executive_observation_id],
                "interpretation": self.executive_interpretation, "supporting_passage_ids": self.executive_passage_ids},
            "primary_finding": {"interpretation": self.primary_interpretation,
                "supporting_passage_ids": self.primary_passage_ids,
                "alternative_explanation": self.primary_alternative_explanation, "limitations": self.primary_limitations},
            "findings": [{"observation_ids": [self.additional_observation_id],
                "interpretation": self.additional_interpretation, "supporting_passage_ids": self.additional_passage_ids,
                "alternative_explanation": self.additional_alternative_explanation, "limitations": self.additional_limitations}],
            "risks": [{"interpretation": self.risk_interpretation, "supporting_passage_ids": self.risk_passage_ids,
                "limitations": self.risk_limitations}],
            "unanswered_questions": self.unanswered_questions,
        }

    @classmethod
    def from_compact(cls, payload):
        """Exact inverse for offline SDK rehearsals; refuse to drop findings/risks."""
        from .focused_briefing import FocusedBriefingInterpretation
        payload = FocusedBriefingInterpretation.model_validate(payload).model_dump(mode="json")
        if len(payload["findings"]) != 1 or len(payload["risks"]) != 1:
            raise ValueError("Flat wire format requires one primary, one additional finding and one risk.")
        executive, primary, additional, risk = (payload["executive_interpretation"], payload["primary_finding"],
            payload["findings"][0], payload["risks"][0])
        def limitations(row):
            value = row["limitations"]
            return [value] if isinstance(value, str) else value
        return cls(executive_observation_id=executive["observation_ids"][0],
            executive_interpretation=executive["interpretation"], executive_passage_ids=executive["supporting_passage_ids"],
            primary_interpretation=primary["interpretation"], primary_passage_ids=primary["supporting_passage_ids"],
            primary_alternative_explanation=primary["alternative_explanation"], primary_limitations=limitations(primary),
            additional_observation_id=additional["observation_ids"][0], additional_interpretation=additional["interpretation"],
            additional_passage_ids=additional["supporting_passage_ids"],
            additional_alternative_explanation=additional["alternative_explanation"], additional_limitations=limitations(additional),
            risk_interpretation=risk["interpretation"], risk_passage_ids=risk["supporting_passage_ids"],
            risk_limitations=limitations(risk), unanswered_questions=payload["unanswered_questions"])


GEMINI_FLAT_FORMAT = """
NATIVE FLAT RESPONSE FORMAT — only the serialization layout changes:
Return a direct JSON object matching the API's flat response schema, with text
as JSON strings and ID/limitation/question lists as arrays of strings. Do not
return result_json, serialized nested JSON or wrapper objects around strings.
executive_* fields describe the executive interpretation and its citations.
primary_* fields interpret Python's primary_observation_id; do not assign an ID.
additional_* fields describe exactly one DIFFERENT observation from
additional_observation_ids. Use required_additional_observation_id when supplied;
otherwise choose the most informative complementary finding. Python checks this
selection without claiming to score the interpretation's economic quality.
risk_* fields describe one material company-specific risk with passage support.
Each limitations array has one to three concise strings within the original
combined length limit. unanswered_questions remains a string array.
Python maps these flat fields to the original compact Pydantic model and applies
all its numerical, period, ID, quotation and financial overclaim checks.
Do not equate OCF drivers such as cash taxes with revenue or operating-income
drivers. Cite only what a passage actually states; planned investment does not
establish historical causes, and gains/losses are not automatically proven noncash.
"""


class GeminiFindingFields(BaseModel):
    """Prospective finding-only wire contract; Python owns the executive."""
    model_config = ConfigDict(extra="forbid", strict=True, revalidate_instances="always")
    primary_interpretation: str
    primary_passage_ids: list[str]
    primary_alternative_explanation: str
    primary_limitations: list[str]
    additional_observation_id: str
    additional_interpretation: str
    additional_passage_ids: list[str]
    additional_alternative_explanation: str
    additional_limitations: list[str]
    risk_interpretation: str
    risk_passage_ids: list[str]
    risk_limitations: list[str]
    unanswered_questions: list[str]

    def compact_payload(self):
        return {
            "primary_finding": {"interpretation": self.primary_interpretation,
                "supporting_passage_ids": self.primary_passage_ids,
                "alternative_explanation": self.primary_alternative_explanation, "limitations": self.primary_limitations},
            "findings": [{"observation_ids": [self.additional_observation_id],
                "interpretation": self.additional_interpretation, "supporting_passage_ids": self.additional_passage_ids,
                "alternative_explanation": self.additional_alternative_explanation, "limitations": self.additional_limitations}],
            "risks": [{"interpretation": self.risk_interpretation, "supporting_passage_ids": self.risk_passage_ids,
                "limitations": self.risk_limitations}], "unanswered_questions": self.unanswered_questions,
        }

    @classmethod
    def from_compact(cls, payload):
        from .focused_briefing import FindingInterpretations
        payload = FindingInterpretations.model_validate(payload).model_dump(mode="json")
        if len(payload["findings"]) != 1 or len(payload["risks"]) != 1:
            raise ValueError("Flat finding format requires one primary, one additional finding and one risk.")
        primary, additional, risk = payload["primary_finding"], payload["findings"][0], payload["risks"][0]
        def limitations(row):
            return [row["limitations"]] if isinstance(row["limitations"], str) else row["limitations"]
        return cls(primary_interpretation=primary["interpretation"], primary_passage_ids=primary["supporting_passage_ids"],
            primary_alternative_explanation=primary["alternative_explanation"], primary_limitations=limitations(primary),
            additional_observation_id=additional["observation_ids"][0], additional_interpretation=additional["interpretation"],
            additional_passage_ids=additional["supporting_passage_ids"], additional_alternative_explanation=additional["alternative_explanation"],
            additional_limitations=limitations(additional), risk_interpretation=risk["interpretation"],
            risk_passage_ids=risk["supporting_passage_ids"], risk_limitations=limitations(risk),
            unanswered_questions=payload["unanswered_questions"])
