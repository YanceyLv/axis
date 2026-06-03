from fastapi import APIRouter

from app.errors import ApiError
from app.models import KnowledgeCase
from app.store import store


router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("/{case_id}", response_model=KnowledgeCase)
def get_knowledge_case(case_id: str) -> KnowledgeCase:
    for knowledge_case in store.knowledge_cases:
        if knowledge_case.id == case_id:
            return knowledge_case

    raise ApiError(
        status_code=404,
        code="KNOWLEDGE_CASE_NOT_FOUND",
        message="Knowledge case not found",
        details={"caseId": case_id},
    )
