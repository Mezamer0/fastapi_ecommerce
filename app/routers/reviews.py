from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.sql import func

from app.db_depends import get_async_db
from app.schemas import ReviewCreate, Review as ReviewSchema, Product
from app.models import Review as ReviewModel, User as UserModel, Product as ProductModel
from app.auth import get_current_buyer, get_current_buyer_or_admin

router = APIRouter(
    prefix="/reviews",
    tags=["reviews"],
)

@router.get("/", response_model=list[ReviewSchema])
async def read_all_reviews(db: AsyncSession = Depends(get_async_db)):
    res = await db.scalars(select(ReviewModel).where(ReviewModel.is_active == True))
    result = res.all()
    return result

@router.post("/", response_model=ReviewSchema)
async def create_review(review: ReviewCreate, db: AsyncSession = Depends(get_async_db), current_user: UserModel = Depends(get_current_buyer)):
    #Проверяем активен ли товар
    stmt = select(ProductModel).where(ProductModel.id == review.product_id, ProductModel.is_active == True)
    res = await db.scalars(stmt)
    result = res.first()
    if result is None:
        HTTPException(status_code=400, detail="Product not found or inactive")

    db_review = ReviewModel(**review.model_dump(), user_id=current_user.id)
    db.add(db_review)
    await db.commit()
    await db.refresh(db_review)

    # Получаем текущий рейтинг товара
    stmt = select(func.avg(ReviewModel.grade)).where(ReviewModel.product_id == review.product_id,
                                                     ReviewModel.is_active == True)
    avg_grade = await db.scalar(stmt)

    # обновляем рейтинг
    stmt = update(ProductModel).where(ProductModel.id == review.product_id, ProductModel.is_active == True).values(
        rating=avg_grade)
    await db.execute(stmt)
    await db.commit()

    return db_review

@router.get("/{product_id}/reviews", response_model=list[ReviewSchema])
async def get_reviews(product_id: int, db: AsyncSession = Depends(get_async_db)):
    # Проверяем активен ли товар
    stmt = select(ProductModel).where(ProductModel.id == product_id, ProductModel.is_active == True)
    res = await db.scalars(stmt)
    result = res.first()
    if result is None:
        HTTPException(status_code=404, detail="Product not found or inactive")

    #Получаем все отзывы
    stmt = select(ReviewModel).where(ReviewModel.product_id == product_id, ReviewModel.is_active == True)
    res = await db.scalars(stmt)
    return res.all()

@router.delete("/{review_id}", response_model=dict)
async def delete_review(review_id: int, db: AsyncSession = Depends(get_async_db), user: UserModel = Depends(get_current_buyer_or_admin)):
    stmt = select(ReviewModel).where(ReviewModel.id == review_id, ReviewModel.is_active == True)
    res = await db.scalars(stmt)
    rev = res.first()
    if rev is None:
        HTTPException(status_code=404, detail="Review not found or inactive")

    if not (user.role == "buyer" and user.id == rev.user_id) or not user.role == "admin":
        HTTPException(status_code=403, detail="Only buyer or admin can perform this action")

    stmt = update(ReviewModel).where(ReviewModel.id == review_id, ReviewModel.is_active == True).values(is_active=False)
    await db.execute(stmt)
    await db.commit()

    # Получаем текущий рейтинг товара
    stmt = select(func.avg(ReviewModel.grade)).where(ReviewModel.product_id == rev.product_id,
                                                     ReviewModel.is_active == True)
    avg_grade = await db.scalar(stmt)

    # обновляем рейтинг
    stmt = update(ProductModel).where(ProductModel.id == rev.product_id, ProductModel.is_active == True).values(
        rating=avg_grade)
    await db.execute(stmt)
    await db.commit()

    return {"message": "Review deleted"}