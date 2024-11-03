from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel, Field, Session, create_engine, select
from typing import List, Dict
from collections import defaultdict
import os

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Define the database model
class Selection(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    user_id: str = Field(index=True, unique=True)
    country: str  # Added country field
    salary: int
    people: int
    work: int

# Create the database engine
DATABASE_URL = "sqlite:///database.db"
engine = create_engine(DATABASE_URL, echo=True)

# Create the database tables
SQLModel.metadata.create_all(engine)

# Mount static files - update the mounting structure
app.mount("/static", StaticFiles(directory="static"), name="static")

# Remove the separate CSS mount as it's included in the static directory
# app.mount("/css", StaticFiles(directory="static/css"), name="css")

@app.exception_handler(500)
async def internal_error_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"message": "Internal server error"}
    )

@app.get("/")
async def read_root():
    return FileResponse(os.path.join("static", "index.html"))

@app.get("/results")
async def read_results():
    return FileResponse(os.path.join("static", "results.html"))

@app.post("/submit")
async def submit_selection(selection: dict):
    user_id = selection.get("user_id")
    country = selection.get("country")  # Retrieve country
    proximities = selection.get("proximities")
    
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID missing")
    if not country:
        raise HTTPException(status_code=400, detail="Country data missing")  # Validate country
    if not proximities:
        raise HTTPException(status_code=400, detail="Proximities data missing")

    # Extract proximities
    try:
        salary = next(item["proximity"] for item in proximities if item["label"] == "Salary")
        people = next(item["proximity"] for item in proximities if item["label"] == "People")
        work = next(item["proximity"] for item in proximities if item["label"] == "Work")
        
        # Add value range validation
        for value in [salary, people, work]:
            if not (1 <= value <= 10):
                raise HTTPException(
                    status_code=400, 
                    detail="All proximity values must be between 1 and 10"
                )
    except StopIteration:
        raise HTTPException(status_code=400, detail="Invalid labels in proximities")
    
    with Session(engine) as session:
        statement = select(Selection).where(Selection.user_id == user_id)
        existing_selection = session.exec(statement).first()
        
        if existing_selection:
            # Update existing selection
            existing_selection.salary = salary
            existing_selection.people = people
            existing_selection.work = work
            existing_selection.country = country  # Update country
            session.add(existing_selection)
            session.commit()
            session.refresh(existing_selection)
            return {"id": existing_selection.id, "message": "Selection updated successfully."}
        else:
            # Create new selection
            new_selection = Selection(user_id=user_id, country=country, salary=salary, people=people, work=work)  # Include country
            session.add(new_selection)
            session.commit()
            session.refresh(new_selection)
            return {"id": new_selection.id, "message": "Selection submitted successfully."}

@app.get("/api/results")
async def get_results():
    try:
        with Session(engine) as session:
            statement = select(Selection)
            selections = session.exec(statement).all()
        
        if not selections:
            return JSONResponse(content=[])

        # Group selections by country
        country_data: Dict[str, List[Selection]] = defaultdict(list)  # Fixed unmatched ']'
        for selection in selections:
            country_data[selection.country].append(selection)

        # Calculate average proximities and participant count per country
        results = []
        for country, selections in country_data.items():
            total_salary = sum(s.salary for s in selections)
            total_people = sum(s.people for s in selections)
            total_work = sum(s.work for s in selections)
            count = len(selections)
            avg_salary = total_salary / count
            avg_people = total_people / count
            avg_work = total_work / count

            results.append({
                "country": country,
                "proximities": [
                    {"label": "Salary", "average": avg_salary},
                    {"label": "People", "average": avg_people},
                    {"label": "Work", "average": avg_work}
                ],
                "participantCount": count  # Added participant count
            })

        return JSONResponse(content=results)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error fetching results")
