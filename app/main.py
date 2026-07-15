from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.models import AnalyzeRequest, AnalyzeResponse, CreateVoiceRequest, CreateVoiceResponse, DeleteVoiceResponse, ExtractProductRequest, ExtractProductResponse, GenerateAnalysisRequest, GenerateAnalysisResponse, GenerateScriptRequest, GenerateScriptResponse, GenerateVoiceRequest, GenerateVoiceResponse, UpdateScriptRequest, VoiceProfile
from app.services.ai import generate_analysis
from app.services.scraper import fetch_product_evidence
from app.services.storage import delete_result_record, list_result_records, load_result_record, save_analysis_result, update_script_text
from app.services.voices import create_voice_profile, delete_voice_profile, list_voice_profiles
from app.workflows.product_graph import run_analyze_product, run_extract_product, run_generate_script, run_generate_voice

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
OUTPUT_DIR = STATIC_DIR / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="AI Product Analysis Assistant", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/r/{task_id}")
def saved_result_page(task_id: str) -> FileResponse:
    if load_result_record(task_id) is None:
        raise HTTPException(status_code=404, detail="保存记录不存在")
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/extract-product", response_model=ExtractProductResponse)
def extract_product(request: ExtractProductRequest) -> ExtractProductResponse:
    return run_extract_product(request)


@app.post("/api/analyze-product", response_model=GenerateAnalysisResponse)
def analyze_product(request: GenerateAnalysisRequest) -> GenerateAnalysisResponse:
    return run_analyze_product(request)


@app.post("/api/generate-script", response_model=GenerateScriptResponse)
def generate_script(request: GenerateScriptRequest) -> GenerateScriptResponse:
    return run_generate_script(request)


@app.post("/api/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    source_url = str(request.url) if request.url else "manual://input"
    evidence = fetch_product_evidence(source_url if request.url else None, request.manual_text, input_method=request.input_method)
    response = generate_analysis(evidence)
    save_analysis_result(source_url, response)
    return response


@app.get("/api/results")
def get_saved_results() -> dict:
    return {"records": list_result_records()}


@app.get("/api/voices", response_model=list[VoiceProfile])
def get_voices() -> list[VoiceProfile]:
    return list_voice_profiles()


@app.post("/api/voices", response_model=CreateVoiceResponse)
def create_voice(request: CreateVoiceRequest) -> CreateVoiceResponse:
    return create_voice_profile(request)


@app.delete("/api/voices/{voice_id}", response_model=DeleteVoiceResponse)
def delete_voice(voice_id: str) -> DeleteVoiceResponse:
    return delete_voice_profile(voice_id)


@app.get("/api/results/{task_id}")
def get_saved_result(task_id: str) -> dict:
    record = load_result_record(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="保存记录不存在")
    return record


@app.patch("/api/results/{task_id}/script", response_model=GenerateScriptResponse)
def update_saved_script(task_id: str, request: UpdateScriptRequest) -> GenerateScriptResponse:
    return update_script_text(task_id, request.hook, request.script)


@app.delete("/api/results/{task_id}")
def delete_saved_result(task_id: str) -> dict:
    if not delete_result_record(task_id):
        raise HTTPException(status_code=404, detail="保存记录不存在")
    return {"deleted": True, "task_id": task_id}


@app.post("/api/generate-voice", response_model=GenerateVoiceResponse)
def generate_voice(request: GenerateVoiceRequest) -> GenerateVoiceResponse:
    return run_generate_voice(request)


@app.exception_handler(ValueError)
def value_error_handler(_, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})
