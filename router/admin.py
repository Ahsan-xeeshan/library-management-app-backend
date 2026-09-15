from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from database import SessionLocal
from datetime import timedelta ,datetime, timezone
from models import Users, Books, Reservations, IssueRecords
from sqlalchemy.orm import Session
from fastapi.responses import JSONResponse
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from jose import jwt, JWTError
from  router.auth import get_current_user
import models

router = APIRouter()

class BookCreate(BaseModel):
    title: str
    author: str
    genre: str
    description: str = Field(default='', max_length=2000)
    price: float = Field(default=0.0, ge=0)
    total_copies : int = Field(default=1)

class UpdateBook(BaseModel):
    title: Optional[str] = Field(default=None)
    author: Optional[str] = Field(default=None)
    genre : Optional[str] = Field(default=None)
    total_copies:Optional[int] = Field(default=None)
    price: Optional[float] = Field(default=None)
    description: Optional[str] = Field(default=None)
    available_copies: Optional[int] = Field(default=None)


class IssueBook(BaseModel):
    book_id: int
    user_id: int

    

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

db_dependency = Annotated[Session, Depends(get_db)]
user_dependency = Annotated[dict, Depends(get_current_user)]


FINE_PER_DAY = 20

def calculate_fine(due_date: datetime, return_date: datetime):
      overdue_days = (return_date.date() - due_date.date()).days
      if overdue_days > 0:
          return round(overdue_days * FINE_PER_DAY,2)
      else: 
          return 0.0




@router.post('/admin/create_book')
def create_book(user: user_dependency, db:db_dependency, new_book: BookCreate):
     if user is None or user.get('role')!= 'librarian': 
         raise HTTPException(status_code=401, detail='Failed Authentication')

     book_model = Books(
         **new_book.model_dump(),
         available_copies = new_book.total_copies
     )
     db.add(book_model)
     db.commit()

     return JSONResponse(status_code=201, content={"message": 'Book added successfully'})
    



@router.put('/admin/update_book/{book_id}')
def update_book(user:user_dependency, db:db_dependency, update_book: UpdateBook, book_id: int):
     if user is None or user.get('role')!= 'librarian': 
             raise HTTPException(status_code=401, detail='Failed Authentication')

     book = db.query(Books).filter(Books.id == book_id).first()

     if book is None: 
          raise HTTPException(status_code = 404, detail='Book not found')

     update_data = update_book.model_dump(exclude_unset=True)

     for key, value in update_data.items():
          setattr(book,key,value)
     db.commit()

     return JSONResponse(status_code=200, content={'message': 'Book Updated successfully'})


@router.delete('/admin/delete_book/{book_id}')
def delete_book(user:user_dependency, db: db_dependency, book_id: int):
     if user is None or user.get('role')!= 'librarian': 
                  raise HTTPException(status_code=401, detail='Failed Authentication')

     book = db.query(Books).filter(Books.id == book_id).first()
     
     if book is None: 
               raise HTTPException(status_code = 404, detail='Book not found')

     db.query(Books).filter(Books.id == book_id).delete()

     db.commit()

     return JSONResponse(status_code=200, content={'message': 'Book deleted successfully'})

@router.get('/admin/reservations')
def get_reservations(
    user: user_dependency,
    db: db_dependency
):
    if user is None or user.get('role') != 'librarian':
        raise HTTPException(
            status_code=401,
            detail='Failed Authentication'
        )

    reservations = db.query(Reservations).order_by(
        Reservations.id.desc()
    ).all()

    result = []

    for reservation in reservations:

        book = db.query(Books).filter(
            Books.id == reservation.book_id
        ).first()

        member = db.query(Users).filter(
            Users.id == reservation.user_id
        ).first()

        result.append({
            'id': reservation.id,

            'book_id': reservation.book_id,
            'book_title': book.title if book else 'Unknown Book',

            'user_id': reservation.user_id,
            'member_name': (
                f"{member.first_name} {member.last_name}"
                if member
                else 'Unknown Member'
            ),
            'member_email': (
                member.email
                if member
                else ''
            ),

            'reservation_date': (
                reservation.reservation_date.isoformat()
                if reservation.reservation_date
                else None
            ),

            'status': reservation.status
        })

    return result


@router.post('/admin/issue_book')
def create_issue(
    user: user_dependency,
    db: db_dependency,
    issue_request: IssueBook
):
    if user is None or user.get('role') != 'librarian':
        raise HTTPException(
            status_code=401,
            detail='Failed Authentication'
        )

    # -----------------------------
    # Find book
    # -----------------------------

    book = db.query(Books).filter(
        Books.id == issue_request.book_id
    ).first()

    if book is None:
        raise HTTPException(
            status_code=404,
            detail='Book not found'
        )

    # -----------------------------
    # Find member
    # -----------------------------

    member = db.query(Users).filter(
        Users.id == issue_request.user_id
    ).first()

    if member is None:
        raise HTTPException(
            status_code=404,
            detail='Member not found'
        )

    # -----------------------------
    # Check existing reservation
    # -----------------------------

    reservation = db.query(Reservations).filter(
        Reservations.book_id == issue_request.book_id,
        Reservations.user_id == issue_request.user_id,
        Reservations.status == 'pending'
    ).first()

    # -----------------------------
    # Check available copy
    # -----------------------------

    if reservation is None and book.available_copies <= 0:
        raise HTTPException(
            status_code=400,
            detail='No copy available'
        )

    # -----------------------------
    # Create issue record
    # -----------------------------

    issue_date = datetime.now()
    loan_days = 14

    issue_model = IssueRecords(
        book_id=issue_request.book_id,
        user_id=issue_request.user_id,
        issue_date=issue_date,
        due_date=issue_date + timedelta(days=loan_days),
        status='issued'
    )

    # -----------------------------
    # Reservation exists
    # -----------------------------

    if reservation is not None:

        # The reservation already reduced
        # available_copies.
        #
        # Therefore DON'T reduce it again.

        reservation.status = 'approved'

    # -----------------------------
    # No reservation
    # -----------------------------

    else:

        # Oral/direct request.
        #
        # This copy wasn't previously reserved,
        # so reduce available copies now.

        book.available_copies -= 1

    db.add(issue_model)

    db.commit()

    return JSONResponse(
        status_code=200,
        content={
            'message': 'Book issued successfully',
            'issue_id': issue_model.id,
            'reserved': reservation is not None
        }
    )

@router.put('/reservations/cancel/{reservation_id}')
def cancel_reservation(
    user: user_dependency,
    db: db_dependency,
    reservation_id: int
):
    if user is None:
        raise HTTPException(
            status_code=401,
            detail='Failed to authenticate'
        )

    reservation = db.query(Reservations).filter(
        Reservations.id == reservation_id,
        Reservations.user_id == user.get('id'),
        Reservations.status == 'pending'
    ).first()

    if reservation is None:
        raise HTTPException(
            status_code=404,
            detail='Reservation not found'
        )

    book = db.query(Books).filter(
        Books.id == reservation.book_id
    ).first()

    if book is not None:
        book.available_copies += 1

    reservation.status = 'canceled'

    db.commit()

    return JSONResponse(
        status_code=200,
        content={
            'message': 'Reservation canceled successfully'
        }
    )

@router.put('/admin/fine/pay/{issue_id}')
def pay_fine(
    user: user_dependency,
    db: db_dependency,
    issue_id: int
):
    if user is None or user.get('role') != 'librarian':
        raise HTTPException(
            status_code=401,
            detail='Failed Authentication'
        )

    issue = db.query(IssueRecords).filter(
        IssueRecords.id == issue_id
    ).first()

    if issue is None:
        raise HTTPException(
            status_code=404,
            detail='No issue found'
        )

    if issue.fine_amount <= 0:
        raise HTTPException(
            status_code=400,
            detail='No fine to pay'
        )

    if issue.fine_paid:
        raise HTTPException(
            status_code=400,
            detail='Fine already paid'
        )

    issue.fine_paid = True

    db.commit()

    return JSONResponse(
        status_code=200,
        content={
            'message': 'Fine paid successfully'
        }
    )