import datetime
import io

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..deps import get_current_user
from ..models import Account, Budget, Category, Transaction, User
from ..ui import templates

router = APIRouter()


def _money(value) -> float:
    return float(value or 0)


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    now = datetime.date.today()
    month_start = now.replace(day=1)
    month_end = (month_start.replace(month=month_start.month % 12 + 1, day=1) - datetime.timedelta(days=1)) \
        if month_start.month != 12 else now.replace(month=1, day=1) - datetime.timedelta(days=1)

    txs = db.query(Transaction).filter(
        Transaction.user_id == user.id,
        Transaction.date >= month_start,
        Transaction.date <= month_end,
    ).options(joinedload(Transaction.category)).all()

    income = sum(_money(t.amount) for t in txs if t.type == "income")
    expense = sum(_money(t.amount) for t in txs if t.type == "expense")

    # Category breakdown for chart
    by_category: dict[str, float] = {}
    for t in txs:
        if t.type == "expense":
            name = t.category.name if t.category else "Tanpa kategori"
            by_category[name] = by_category.get(name, 0) + _money(t.amount)

    recent = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.id)
        .options(joinedload(Transaction.category), joinedload(Transaction.account))
        .order_by(Transaction.date.desc(), Transaction.created_at.desc())
        .limit(10)
        .all()
    )

    return templates.TemplateResponse(request, "dashboard.html", {
        "user": user, "month": now.strftime("%B %Y"), "income": income, "expense": expense,
        "balance": income - expense, "by_category": by_category, "recent": recent,
    })


@router.get("/transactions", response_class=HTMLResponse)
def transactions_page(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    txs = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.id)
        .options(joinedload(Transaction.category), joinedload(Transaction.account))
        .order_by(Transaction.date.desc(), Transaction.created_at.desc())
        .all()
    )
    categories = db.query(Category).filter(Category.user_id == user.id).order_by(Category.name).all()
    accounts = db.query(Account).filter(Account.user_id == user.id).order_by(Account.name).all()
    return templates.TemplateResponse(request, "transactions.html", {
        "user": user, "transactions": txs, "categories": categories, "accounts": accounts,
    })


@router.post("/transactions")
def transaction_create(
    request: Request,
    date: str = Form(...),
    type: str = Form(...),
    amount: str = Form(...),
    category_id: str = Form(""),
    account_id: str = Form(""),
    note: str = Form(""),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        amount_value = float(amount.replace(".", "").replace(",", "."))
        if amount_value <= 0:
            raise ValueError
    except ValueError:
        return RedirectResponse("/transactions?error=amount", status_code=303)

    db.add(Transaction(
        user_id=user.id,
        date=datetime.date.fromisoformat(date),
        type=type if type in ("income", "expense") else "expense",
        amount=amount_value,
        category_id=category_id or None,
        account_id=account_id or None,
        note=note.strip() or None,
    ))
    db.commit()
    return RedirectResponse("/transactions", status_code=303)


@router.post("/transactions/{tx_id}/delete")
def transaction_delete(tx_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    tx = db.get(Transaction, tx_id)
    if tx and tx.user_id == user.id:
        db.delete(tx)
        db.commit()
    return RedirectResponse("/transactions", status_code=303)


@router.post("/categories")
def category_create(
    name: str = Form(...), type: str = Form("expense"),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    name = name.strip()
    if name:
        exists = db.query(Category).filter(Category.user_id == user.id, Category.name == name).first()
        if not exists:
            db.add(Category(user_id=user.id, name=name, type=type))
            db.commit()
    return RedirectResponse("/transactions", status_code=303)


@router.post("/accounts")
def account_create(
    name: str = Form(...),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    name = name.strip()
    if name:
        exists = db.query(Account).filter(Account.user_id == user.id, Account.name == name).first()
        if not exists:
            db.add(Account(user_id=user.id, name=name))
            db.commit()
    return RedirectResponse("/transactions", status_code=303)


@router.get("/budgets", response_class=HTMLResponse)
def budgets_page(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    now = datetime.date.today()
    month = now.strftime("%Y-%m")
    budgets = (
        db.query(Budget)
        .filter(Budget.user_id == user.id, Budget.month == month)
        .options(joinedload(Budget.category))
        .all()
    )
    spent: dict[str, float] = {}
    for b in budgets:
        total = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.user_id == user.id,
            Transaction.type == "expense",
            Transaction.category_id == b.category_id,
            Transaction.date >= now.replace(day=1),
        ).scalar()
        spent[b.category_id] = float(total or 0)

    categories = db.query(Category).filter(
        Category.user_id == user.id, Category.type == "expense"
    ).order_by(Category.name).all()
    return templates.TemplateResponse(request, "budgets.html", {
        "user": user, "month": month, "budgets": budgets, "spent": spent, "categories": categories,
    })


@router.post("/budgets")
def budget_create(
    category_id: str = Form(...), limit: str = Form(...),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    try:
        limit_value = float(limit.replace(".", "").replace(",", "."))
        if limit_value <= 0:
            raise ValueError
    except ValueError:
        return RedirectResponse("/budgets?error=limit", status_code=303)

    month = datetime.date.today().strftime("%Y-%m")
    existing = db.query(Budget).filter(
        Budget.user_id == user.id, Budget.category_id == category_id, Budget.month == month
    ).first()
    if existing:
        existing.limit = limit_value
    else:
        db.add(Budget(user_id=user.id, category_id=category_id, month=month, limit=limit_value))
    db.commit()
    return RedirectResponse("/budgets", status_code=303)


@router.post("/budgets/{budget_id}/delete")
def budget_delete(budget_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    b = db.get(Budget, budget_id)
    if b and b.user_id == user.id:
        db.delete(b)
        db.commit()
    return RedirectResponse("/budgets", status_code=303)


@router.get("/reports", response_class=HTMLResponse)
def reports_page(
    request: Request,
    month: str = "",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    now = datetime.date.today()
    month = month or now.strftime("%Y-%m")
    txs = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.id, func.to_char(Transaction.date, "YYYY-MM") == month)
        .options(joinedload(Transaction.category), joinedload(Transaction.account))
        .order_by(Transaction.date.desc())
        .all()
    )
    total_income = sum(_money(t.amount) for t in txs if t.type == "income")
    total_expense = sum(_money(t.amount) for t in txs if t.type == "expense")

    per_category: dict[str, float] = {}
    per_account: dict[str, float] = {}
    for t in txs:
        key = t.category.name if t.category else "Tanpa kategori"
        per_category[key] = per_category.get(key, 0) + _money(t.amount)
        akey = t.account.name if t.account else "Tanpa akun"
        per_account[akey] = per_account.get(akey, 0) + _money(t.amount)

    return templates.TemplateResponse(request, "reports.html", {
        "user": user, "month": month, "transactions": txs,
        "total_income": total_income, "total_expense": total_expense,
        "per_category": per_category, "per_account": per_account,
    })


@router.get("/export")
def export_csv(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    txs = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.id)
        .options(joinedload(Transaction.category), joinedload(Transaction.account))
        .order_by(Transaction.date)
        .all()
    )
    buffer = io.StringIO()
    buffer.write("date,type,amount,category,account,note\n")
    for t in txs:
        buffer.write(
            f"{t.date},{t.type},{_money(t.amount):.2f},"
            f"{t.category.name if t.category else ''},{t.account.name if t.account else ''},"
            f"{(t.note or '').replace(chr(10), ' ')}\n"
        )
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=transactions.csv"},
    )


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from ..models import Passkey
    passkeys = db.query(Passkey).filter(Passkey.user_id == user.id).all()
    return templates.TemplateResponse(request, "settings.html", {"user": user, "passkeys": passkeys})
