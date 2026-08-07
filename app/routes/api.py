import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..deps import get_api_user, require_write_api_key
from ..models import Account, Budget, Category, Transaction, User
from ..security import rate_limit

router = APIRouter(prefix="/api/v1")


def _money(value) -> float:
    return float(value or 0)


def _parse_date(value: str, field: str) -> datetime.date:
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date for {field}: {value}")


def _find_or_create_category(db: Session, user: User, name: str, type: str) -> Category:
    """Case-insensitive match; create if missing. Existing capitalization is preserved."""
    name = name.strip()
    existing = db.query(Category).filter(
        Category.user_id == user.id,
        func.lower(Category.name) == name.lower(),
    ).first()
    if existing:
        return existing
    cat = Category(user_id=user.id, name=name, type=type)
    db.add(cat)
    db.flush()
    return cat


def _find_or_create_account(db: Session, user: User, name: str) -> Account:
    name = name.strip()
    existing = db.query(Account).filter(
        Account.user_id == user.id,
        func.lower(Account.name) == name.lower(),
    ).first()
    if existing:
        return existing
    acc = Account(user_id=user.id, name=name)
    db.add(acc)
    db.flush()
    return acc


class TransactionCreate(BaseModel):
    date: datetime.date
    type: str = Field(pattern="^(income|expense)$")
    amount: float = Field(gt=0)
    category: str | None = None
    category_id: str | None = None
    account: str | None = None
    account_id: str | None = None
    note: str | None = Field(default=None, max_length=500)


def _tx_dict(t: Transaction) -> dict:
    return {
        "id": t.id, "date": t.date.isoformat(), "type": t.type, "amount": _money(t.amount),
        "category": t.category.name if t.category else None, "category_id": t.category_id,
        "account": t.account.name if t.account else None, "account_id": t.account_id, "note": t.note,
    }


@router.post("/transactions", status_code=201)
def create_transaction(
    payload: TransactionCreate,
    request: Request,
    user: User = Depends(require_write_api_key),
    db: Session = Depends(get_db),
):
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limit(f"write-api:{user.id}", limit=60, window_seconds=60) or not rate_limit(
        f"write-api-ip:{client_ip}", limit=120, window_seconds=60
    ):
        raise HTTPException(status_code=429, detail="Too many write requests")

    if payload.category_id and payload.category:
        raise HTTPException(status_code=422, detail="Provide either category or category_id, not both")

    category = None
    if payload.category_id:
        category = db.get(Category, payload.category_id)
        if not category or category.user_id != user.id:
            raise HTTPException(status_code=422, detail="Unknown category_id")
    elif payload.category:
        category = _find_or_create_category(db, user, payload.category, payload.type)

    account = None
    if payload.account_id and payload.account:
        raise HTTPException(status_code=422, detail="Provide either account or account_id, not both")
    if payload.account_id:
        account = db.get(Account, payload.account_id)
        if not account or account.user_id != user.id:
            raise HTTPException(status_code=422, detail="Unknown account_id")
    elif payload.account:
        account = _find_or_create_account(db, user, payload.account)

    tx = Transaction(
        user_id=user.id, date=payload.date, type=payload.type, amount=payload.amount,
        category_id=category.id if category else None,
        account_id=account.id if account else None,
        note=payload.note.strip() if payload.note else None,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return _tx_dict(tx)


@router.get("/transactions")
def list_transactions(
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    category_id: str | None = None,
    account_id: str | None = None,
    type: str | None = None,
    user: User = Depends(get_api_user),
    db: Session = Depends(get_db),
):
    q = db.query(Transaction).filter(Transaction.user_id == user.id)
    if from_date:
        q = q.filter(Transaction.date >= _parse_date(from_date, "from"))
    if to_date:
        q = q.filter(Transaction.date <= _parse_date(to_date, "to"))
    if category_id:
        q = q.filter(Transaction.category_id == category_id)
    if account_id:
        q = q.filter(Transaction.account_id == account_id)
    if type:
        q = q.filter(Transaction.type == type)
    txs = q.options(joinedload(Transaction.category), joinedload(Transaction.account)).order_by(Transaction.date).all()
    return [
        {
            "id": t.id, "date": t.date.isoformat(), "type": t.type, "amount": _money(t.amount),
            "category": t.category.name if t.category else None,
            "category_id": t.category_id, "account": t.account.name if t.account else None,
            "account_id": t.account_id, "note": t.note,
        }
        for t in txs
    ]


@router.get("/transactions/{tx_id}")
def get_transaction(tx_id: str, user: User = Depends(get_api_user), db: Session = Depends(get_db)):
    t = db.get(Transaction, tx_id)
    if not t or t.user_id != user.id:
        return {"detail": "Not found"}
    return {
        "id": t.id, "date": t.date.isoformat(), "type": t.type, "amount": _money(t.amount),
        "category": t.category.name if t.category else None, "category_id": t.category_id,
        "account": t.account.name if t.account else None, "account_id": t.account_id, "note": t.note,
    }


@router.get("/summary")
def summary(
    month: str | None = None,
    user: User = Depends(get_api_user),
    db: Session = Depends(get_db),
):
    now = datetime.date.today()
    month = month or now.strftime("%Y-%m")
    txs = db.query(Transaction).filter(
        Transaction.user_id == user.id,
        func.to_char(Transaction.date, "YYYY-MM") == month,
    ).all()
    income = sum(_money(t.amount) for t in txs if t.type == "income")
    expense = sum(_money(t.amount) for t in txs if t.type == "expense")
    return {"month": month, "income": income, "expense": expense, "balance": income - expense}


@router.get("/categories")
def list_categories(user: User = Depends(get_api_user), db: Session = Depends(get_db)):
    cats = db.query(Category).filter(Category.user_id == user.id).order_by(Category.name).all()
    return [{"id": c.id, "name": c.name, "type": c.type} for c in cats]


@router.get("/accounts")
def list_accounts(user: User = Depends(get_api_user), db: Session = Depends(get_db)):
    accs = db.query(Account).filter(Account.user_id == user.id).order_by(Account.name).all()
    return [{"id": a.id, "name": a.name} for a in accs]


@router.get("/budgets")
def list_budgets(month: str | None = None, user: User = Depends(get_api_user), db: Session = Depends(get_db)):
    now = datetime.date.today()
    month = month or now.strftime("%Y-%m")
    budgets = (
        db.query(Budget)
        .filter(Budget.user_id == user.id, Budget.month == month)
        .options(joinedload(Budget.category))
        .all()
    )
    result = []
    for b in budgets:
        spent = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.user_id == user.id,
            Transaction.type == "expense",
            Transaction.category_id == b.category_id,
            func.to_char(Transaction.date, "YYYY-MM") == month,
        ).scalar()
        result.append({
            "id": b.id, "month": b.month, "category": b.category.name,
            "category_id": b.category_id, "limit": _money(b.limit), "spent": _money(spent),
        })
    return result
