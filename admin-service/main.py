"""
Admin microservice for the clinic management system.
Aggregates data from all three Spring Boot services and exposes a unified REST API.
"""

import httpx
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()

# ── Service URLs (overridden by env vars in Docker) ──────────────────────────
PATIENTS_URL    = os.getenv("PATIENTS_SERVICE_URL",   "http://localhost:8080")
MEDECINS_URL    = os.getenv("MEDECINS_SERVICE_URL",   "http://localhost:8082")
RENDEZVOUS_URL  = os.getenv("RENDEZVOUS_SERVICE_URL", "http://localhost:8081")
EUREKA_URL      = os.getenv("EUREKA_SERVICE_URL",     "http://localhost:8761")

app = FastAPI(
    title="Clinic Admin API",
    description="Unified admin API aggregating Patients, Médecins and Rendez-vous services.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Serve GUI ─────────────────────────────────────────────────────────────────
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

@app.get("/", include_in_schema=False)
async def serve_gui():
    """Serve the clinic management web GUI."""
    return FileResponse(os.path.join(_STATIC_DIR, "index.html"))

# Mount static assets (JS, CSS, images) — must come AFTER the explicit routes
if os.path.isdir(_STATIC_DIR):
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

# ── Pydantic models ───────────────────────────────────────────────────────────

class Patient(BaseModel):
    id:       Optional[int]  = None
    cin:      str
    fullname: str
    mobile:   str
    age:      int
    gender:   str

class Medecin(BaseModel):
    id:        Optional[int]  = None
    cin:       str
    fullname:  str
    mobile:    str
    gender:    str
    specialite: str

class PatientRef(BaseModel):
    cin:      str
    fullname: str
    mobile:   str
    age:      int
    gender:   str

class MedecinRef(BaseModel):
    fullname: str

class Rendezvous(BaseModel):
    idrendezvous: Optional[int] = None
    date:    Optional[str] = None
    cause:   str
    patient: Optional[str] = None
    medecin: Optional[str] = None

class RendezvousRequest(BaseModel):
    patient:    PatientRef
    medecin:    MedecinRef
    rendezvous: Rendezvous

class RendezvousUpdateRequest(BaseModel):
    """Used for PUT /admin/rendezvous — update an existing appointment."""
    patient:    PatientRef
    medecin:    MedecinRef
    rendezvous: Rendezvous

# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get(url: str):
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.json()

async def _post(url: str, payload: dict):
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        return r.json()

async def _put(url: str, payload: dict):
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.put(url, json=payload)
        r.raise_for_status()
        return r.json()

async def _delete(url: str):
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.delete(url)
        r.raise_for_status()
        return r.text

# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
async def health():
    return {"status": "UP", "service": "admin-service"}

@app.get("/health/services", tags=["Health"])
async def services_health():
    """Check health of all downstream Spring Boot services."""
    results = {}
    for name, base in [
        ("eureka",     EUREKA_URL),
        ("patients",   PATIENTS_URL),
        ("medecins",   MEDECINS_URL),
        ("rendezvous", RENDEZVOUS_URL),
    ]:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{base}/actuator/health")
            results[name] = r.json() if r.status_code == 200 else {"status": "DOWN", "code": r.status_code}
        except Exception as e:
            results[name] = {"status": "UNREACHABLE", "error": str(e)}
    return results

# ── Patients ──────────────────────────────────────────────────────────────────

@app.get("/admin/patients", tags=["Patients"])
async def list_patients():
    """Get all patients."""
    try:
        return await _get(f"{PATIENTS_URL}/patient/getAll")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))

@app.get("/admin/patients/{cin}", tags=["Patients"])
async def get_patient(cin: str):
    """Get a patient by CIN."""
    try:
        return await _get(f"{PATIENTS_URL}/patient/byCIN/{cin}")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))

@app.post("/admin/patients", status_code=status.HTTP_201_CREATED, tags=["Patients"])
async def create_patient(patient: Patient):
    """Add a new patient."""
    try:
        return await _post(f"{PATIENTS_URL}/patient/add", patient.model_dump(exclude_none=True))
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))

@app.put("/admin/patients", tags=["Patients"])
async def update_patient(patient: Patient):
    """Update a patient."""
    try:
        return await _put(f"{PATIENTS_URL}/patient/update", patient.model_dump(exclude_none=True))
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))

@app.delete("/admin/patients/{cin}", tags=["Patients"])
async def delete_patient(cin: str):
    """Delete a patient by CIN."""
    try:
        return await _delete(f"{PATIENTS_URL}/patient/delete/{cin}")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))

# ── Médecins ──────────────────────────────────────────────────────────────────

@app.get("/admin/medecins", tags=["Médecins"])
async def list_medecins():
    """Get all médecins."""
    try:
        return await _get(f"{MEDECINS_URL}/medecin/getAll")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))

@app.get("/admin/medecins/{cin}", tags=["Médecins"])
async def get_medecin(cin: str):
    """Get a médecin by CIN."""
    try:
        return await _get(f"{MEDECINS_URL}/medecin/getByCin/{cin}")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))

@app.post("/admin/medecins", status_code=status.HTTP_201_CREATED, tags=["Médecins"])
async def create_medecin(medecin: Medecin):
    """Add a new médecin."""
    try:
        return await _post(f"{MEDECINS_URL}/medecin/add", medecin.model_dump(exclude_none=True))
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))

@app.put("/admin/medecins", tags=["Médecins"])
async def update_medecin(medecin: Medecin):
    """Update a médecin."""
    try:
        return await _put(f"{MEDECINS_URL}/medecin/update", medecin.model_dump(exclude_none=True))
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))

@app.delete("/admin/medecins/{cin}", tags=["Médecins"])
async def delete_medecin(cin: str):
    """Delete a médecin by CIN."""
    try:
        return await _delete(f"{MEDECINS_URL}/medecin/delete/{cin}")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))

# ── Rendez-vous ───────────────────────────────────────────────────────────────

@app.get("/admin/rendezvous", tags=["Rendez-vous"])
async def list_rendezvous():
    """Get all rendez-vous."""
    try:
        return await _get(f"{RENDEZVOUS_URL}/rendezvous/GetAll")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))

@app.get("/admin/rendezvous/{id}", tags=["Rendez-vous"])
async def get_rendezvous(id: int):
    """Get a rendez-vous by ID (returns full DTO with patient details)."""
    try:
        return await _get(f"{RENDEZVOUS_URL}/rendezvous/findById/{id}")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))

@app.get("/admin/rendezvous/patient/{cin}", tags=["Rendez-vous"])
async def get_rendezvous_by_patient(cin: str):
    """Get all rendez-vous for a patient."""
    try:
        return await _get(f"{RENDEZVOUS_URL}/rendezvous/allByPatient/{cin}")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))

@app.post("/admin/rendezvous", status_code=status.HTTP_201_CREATED, tags=["Rendez-vous"])
async def create_rendezvous(data: RendezvousRequest):
    """Create a rendez-vous (creates patient + links médecin + books appointment)."""
    try:
        return await _post(f"{RENDEZVOUS_URL}/rendezvous/add", data.model_dump(exclude_none=True))
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))

@app.put("/admin/rendezvous", tags=["Rendez-vous"])
async def update_rendezvous(data: RendezvousUpdateRequest):
    """Update a rendez-vous (updates patient + keeps médecin + updates appointment)."""
    try:
        return await _put(f"{RENDEZVOUS_URL}/rendezvous/update", data.model_dump(exclude_none=True))
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))

@app.delete("/admin/rendezvous/{id}", tags=["Rendez-vous"])
async def delete_rendezvous(id: int):
    """Delete a rendez-vous by ID."""
    try:
        return await _delete(f"{RENDEZVOUS_URL}/rendezvous/delete/{id}")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))

# ── Dashboard summary ─────────────────────────────────────────────────────────

@app.get("/admin/summary", tags=["Dashboard"])
async def summary():
    """Aggregate counts from all services."""
    try:
        patients   = await _get(f"{PATIENTS_URL}/patient/getAll")
        medecins   = await _get(f"{MEDECINS_URL}/medecin/getAll")
        rendezvous = await _get(f"{RENDEZVOUS_URL}/rendezvous/GetAll")
        return {
            "total_patients":   len(patients),
            "total_medecins":   len(medecins),
            "total_rendezvous": len(rendezvous),
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"One or more services unavailable: {e}")
