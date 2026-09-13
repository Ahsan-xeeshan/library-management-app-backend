from typing import Annotated, Optional
from sqlalchemy.orm import Session
from fastapi import FastAPI, Depends, FastAPI, HTTPException
import models
from models import Books,Users, Reservations, IssueRecords
from database import engine,SessionLocal
from fastapi.responses import JSONResponse
from router import auth, admin
from router.auth import get_current_user
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI()

app.include_router(auth.router)
app.include_router(admin.router)

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


models.Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

db_dependency = Annotated[Session, Depends(get_db)]
user_dependency = Annotated[dict, Depends(get_current_user)]


@app.get("/books/all")
def get_all_books(user: user_dependency, db: db_dependency):
    books = db.query(Books).all()
    return books


@app.get("/books/{book_id}")
def get_specific_book(user: user_dependency, db: db_dependency, book_id: int):

    if user is None:
        raise HTTPException(status_code=401, detail="Failed to authenticate user")

    book = db.query(Books).filter(Books.id == book_id).first()
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return book


@app.post("/books/reserve/{book_id}")
def reserve_book(user: user_dependency, db: db_dependency, book_id: int):

    if user is None:
        raise HTTPException(status_code=401, detail="Failed to authenticate user")

    book = db.query(Books).filter(Books.id == book_id).first()

    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")

    if book.available_copies <= 0:
        raise HTTPException(status_code=400, detail="No available copies for reservation")

    # Create a new reservation
    reservation = Reservations(user_id=user.get('id'), book_id=book_id)
    db.add(reservation)

    # Decrease the available copies of the book
    book.available_copies -= 1

    db.commit()
    return JSONResponse(content={"message": "Book reserved successfully", "reservation_id": reservation.id}, status_code=201)

@app.delete("/books/cancel_reservation/{reservation_id}")
def cancel_reservation(user: user_dependency, db: db_dependency, reservation_id: int):  

    if user is None:
        raise HTTPException(status_code=401, detail="Failed to authenticate user")

    reservation = db.query(Reservations).filter(Reservations.id == reservation_id, Reservations.user_id == user.get('id')).first()

    if reservation is None:
        raise HTTPException(status_code=404, detail="Reservation not found")

    # Increase the available copies of the book
    book = db.query(Books).filter(Books.id == reservation.book_id).first()
    if book:
        book.available_copies += 1

    reservation.status = "canceled"
    db.commit()
    return JSONResponse(content={"message": "Reservation canceled successfully"}, status_code=200)


@app.get("/reservations/my")
def get_my_reservations(user: user_dependency, db: db_dependency):

    if user is None:
        raise HTTPException(status_code=401, detail="Failed to authenticate user")

    reservations = db.query(Reservations).filter(Reservations.user_id == user.get('id')).all()
    return reservations


@app.get('/issued_book/my')
def get_my_issued(user:user_dependency, db:db_dependency):
    if user is None:
            raise HTTPException(status_code=401, detail="Failed to authenticate user")

    issues = db.query(IssueRecords).filter(
        IssueRecords.user_id == user.get('id'),
        IssueRecords.status == 'issued'
        ).all()

    return issues