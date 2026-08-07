import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..deps import get_api_user
from ..models import Account, Budget, Category, Transaction, User

router = APIRouter(prefix="/api/v1")


def _money(value) -> float:
    return float(value or 0)


def _parse_date(value: str, field: str) -> datetime.date:
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date for {field}: {value}")


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
