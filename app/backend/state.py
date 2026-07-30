from typing_extensions import TypedDict, Annotated
from app.backend.agent_schemas.report import PriceReport

class MessagesState(TypedDict):
    message: str
    reported_by: str
    price_report: PriceReport