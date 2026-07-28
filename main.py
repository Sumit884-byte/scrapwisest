from fastapi import FastAPI
from pydantic import BaseModel

from supervisor import submit_report, query_price
import store

app = FastAPI(title="ScrapSense")


class ReportRequest(BaseModel):
    message: str
    reported_by: str


@app.post("/report")
def report(req: ReportRequest):
    return submit_report(req.message, req.reported_by)


@app.get("/reports")
def reports():
    return store.all_reports()


@app.get("/price")
def price(material: str, location: str):
    return query_price(material, location)
