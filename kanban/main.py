from fastapi import FastAPI
from .kanban import router

app = FastAPI(title="Kanban Board")

# We include the router without a prefix so that when run locally,
# the board opens directly at the root ('/')
app.include_router(router)