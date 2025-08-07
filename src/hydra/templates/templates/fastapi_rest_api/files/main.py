from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
{% if include_auth %}from fastapi.middleware.cors import CORSMiddleware{% endif %}
from sqlalchemy.orm import Session
from database import get_db, engine
from models import Base
from schemas import ItemCreate, ItemResponse
from crud import create_item, get_items, get_item
{% if include_auth %}from auth import verify_token{% endif %}

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="{{project_name}} API",
    description="API for {{project_name}}",
    version="{{version}}"
)

{% if include_auth %}
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    payload = verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    return payload
{% endif %}

@app.get("/")
async def root():
    return {"message": "Welcome to {{project_name}} API", "version": "{{version}}"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "{{project_name}}"}

@app.post("/items/", response_model=ItemResponse)
def create_new_item(
    item: ItemCreate,
    db: Session = Depends(get_db){% if include_auth %},
    current_user: dict = Depends(get_current_user){% endif %}
):
    return create_item(db=db, item=item)

@app.get("/items/", response_model=list[ItemResponse])
def read_items(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db){% if include_auth %},
    current_user: dict = Depends(get_current_user){% endif %}
):
    return get_items(db, skip=skip, limit=limit)

@app.get("/items/{item_id}", response_model=ItemResponse)
def read_item(
    item_id: int,
    db: Session = Depends(get_db){% if include_auth %},
    current_user: dict = Depends(get_current_user){% endif %}
):
    db_item = get_item(db, item_id=item_id)
    if db_item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return db_item