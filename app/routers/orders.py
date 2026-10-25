from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models import Customer, Order, OrderItem, Product
from app.schemas import OrderCreate, OrderRead

router = APIRouter(
    prefix="/orders", tags=["orders"], dependencies=[Depends(get_current_user)]
)


@router.post("", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
def create_order(payload: OrderCreate, db: Session = Depends(get_db)) -> Order:
    if db.get(Customer, payload.customer_id) is None:
        raise HTTPException(status_code=404, detail="Client introuvable")

    quantities: dict[int, int] = {}
    for item in payload.items:
        quantities[item.product_id] = quantities.get(item.product_id, 0) + item.quantity

    products: dict[int, Product] = {}
    for product_id in sorted(quantities):
        product = db.scalar(
            select(Product).where(Product.id == product_id).with_for_update()
        )
        if product is None:
            db.rollback()
            raise HTTPException(status_code=404, detail=f"Produit {product_id} introuvable")
        if product.stock_quantity < quantities[product_id]:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail=f"Stock insuffisant pour le produit {product.name}",
            )
        products[product_id] = product

    order_items = [
        OrderItem(
            product_id=item.product_id,
            quantity=item.quantity,
            unit_price=products[item.product_id].price,
        )
        for item in payload.items
    ]
    total = sum(
        (Decimal(item.quantity) * products[item.product_id].price for item in payload.items),
        start=Decimal("0.00"),
    )
    order = Order(
        customer_id=payload.customer_id,
        total_amount=total,
        items=order_items,
    )
    for product_id, quantity in quantities.items():
        products[product_id].stock_quantity -= quantity

    db.add(order)
    db.commit()
    db.refresh(order)
    return order


@router.get("", response_model=list[OrderRead])
def list_orders(db: Session = Depends(get_db)) -> list[Order]:
    statement = (
        select(Order)
        .options(selectinload(Order.items))
        .order_by(Order.created_at.desc(), Order.id.desc())
    )
    return list(db.scalars(statement))


@router.get("/{order_id}", response_model=OrderRead)
def get_order(order_id: int, db: Session = Depends(get_db)) -> Order:
    statement = (
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.id == order_id)
    )
    order = db.scalar(statement)
    if order is None:
        raise HTTPException(status_code=404, detail="Commande introuvable")
    return order
