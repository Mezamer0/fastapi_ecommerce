from datetime import datetime, timedelta
from itertools import product

from asyncpg.pgproto.pgproto import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, update, func
from sqlalchemy.orm import Session

from app.db_depends import get_db
from app.schemas import Product as ProductSchema, ProductCreate, ProductList
from app.models import Product as ProductModel, Category as CategoryModel
from app.models.users import User as UserModel
from app.auth import get_current_seller

from app.db_depends import get_async_db
from sqlalchemy.ext.asyncio import AsyncSession

# Создаём маршрутизатор для товаров
router = APIRouter(
    prefix="/products",
    tags=["products"],
)


@router.get("/", response_model=ProductList, status_code=status.HTTP_200_OK)
async def get_all_products(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        category_id: int | None = Query(
            None, description="ID категории для фильтрации"),
        min_price: float | None = Query(
            None, ge=0, description="Минимальная цена товара"),
        max_price: float | None = Query(
            None, ge=0, description="Максимальная цена товара"),
        in_stock: bool | None = Query(
            None, description="true — только товары в наличии, false — только без остатка"),
        seller_id: int | None = Query(
            None, description="ID продавца для фильтрации"),
        created_at: datetime | None = Query(
            None, description="Дата создания для фильтрации"),
        db: AsyncSession = Depends(get_async_db),
):
    """
    Возвращает список всех активных товаров с поддержкой фильтров.
    """
    # Проверка логики min_price <= max_price
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="min_price не может быть больше max_price")

    # Формируем список фильтров
    filters = [ProductModel.is_active == True]

    if category_id is not None:
        filters.append(ProductModel.category_id == category_id)
    if min_price is not None:
        filters.append(ProductModel.price >= min_price)
    if max_price is not None:
        filters.append(ProductModel.price <= max_price)
    if in_stock is not None:
        filters.append(ProductModel.stock > 0 if in_stock else ProductModel.stock == 0)
    if seller_id is not None:
        filters.append(ProductModel.seller_id == seller_id)
    if created_at is not None:
        filters.extend([ProductModel.created_at >= created_at, ProductModel.created_at < created_at + timedelta(days=1)])

    # Подсчёт общего количества с учётом фильтров
    total_stmt = select(func.count()).select_from(ProductModel).where(*filters)
    total = await db.scalar(total_stmt) or 0

    # Выборка товаров с фильтрами и пагинацией
    products_stmt = (
        select(ProductModel)
        .where(*filters)
        .order_by(ProductModel.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = (await db.scalars(products_stmt)).all()

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/", response_model=ProductSchema, status_code=201)
async def create_product(product: ProductCreate, db: AsyncSession = Depends(get_async_db), current_user: UserModel = Depends(get_current_seller)):
    """
        Создаёт новый товар, привязанный к текущему продавцу (только для 'seller').
    """
    # Проверяем, существует ли активная категория
    stmt = select(CategoryModel).where(CategoryModel.id == product.category_id, CategoryModel.is_active == True)
    res = await db.scalars(stmt)
    res = res.first()
    if res is None:
        raise HTTPException(status_code=400, detail="Category not found or inactive")

    db_product = ProductModel(**product.model_dump(), seller_id=current_user.id)
    db.add(db_product)
    await db.commit()
    await db.refresh(db_product) # Для получения id и is_active из базы
    return db_product


@router.get("/category/{category_id}", response_model=list[ProductSchema], status_code=status.HTTP_200_OK)
async def get_products_by_category(category_id: int, db: AsyncSession = Depends(get_async_db)):
    """
    Возвращает список товаров в указанной категории по её ID.
    """
    # Проверяем, существует ли активная категория
    stmt = select(CategoryModel).where(CategoryModel.id == category_id, CategoryModel.is_active == True)
    res = await db.scalars(stmt)
    res = res.first()
    if res is None:
        raise HTTPException(status_code=404, detail="Category not found or inactive")

    # Получаем активные товары в категории
    stmt = select(ProductModel).where(ProductModel.category_id == category_id, ProductModel.is_active == True)
    res = await db.scalars(stmt)
    return res.all()


@router.get("/{product_id}", response_model=ProductSchema, status_code=status.HTTP_200_OK)
async def get_product(product_id: int, db: AsyncSession = Depends(get_async_db)):
    """
    Возвращает детальную информацию о товаре по его ID.
    """
    # Проверяем, существует ли активный товар
    stmt = select(ProductModel).where(ProductModel.id == product_id, ProductModel.is_active == True)
    prod = await db.scalars(stmt)
    prod = prod.first()
    if prod is None:
        raise HTTPException(status_code=404, detail="Product not found or inactive")

    # Проверяем, существует ли активная категория
    stmt2 = select(CategoryModel).where(CategoryModel.id == prod.category_id, CategoryModel.is_active == True)
    cat = await db.scalars(stmt2)
    cat = cat.first()
    if cat is None:
        raise HTTPException(status_code=404, detail="Category not found or inactive")

    return prod


@router.put("/{product_id}", response_model=ProductSchema, status_code=status.HTTP_200_OK)
async def update_product(product_id: int, product: ProductCreate, db: AsyncSession = Depends(get_async_db), current_user: UserModel = Depends(get_current_seller)):
    """
    Обновляет товар, если он принадлежит текущему продавцу (только для 'seller').
    """
    # Проверяем, существует ли товар
    stmt = select(ProductModel).where(ProductModel.id == product_id, ProductModel.is_active == True)
    prod = await db.scalars(stmt)
    prod = prod.first()
    if prod is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found or inactive")
    if prod.seller_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only update your own products")

    # Проверяем, существует ли активная категория
    stmt = select(CategoryModel).where(CategoryModel.id == prod.category_id, CategoryModel.is_active == True)
    cat = await db.scalars(stmt)
    if cat.first() is None:
        raise HTTPException(status_code=400, detail="Category not found or inactive")

    # Обновляем товар
    await db.execute(
        update(ProductModel).where(ProductModel.id == product_id).values(**product.model_dump())
    )
    await db.commit()
    await db.refresh(prod)
    return prod


@router.delete("/{product_id}", response_model = ProductSchema, status_code=status.HTTP_200_OK)
async def delete_product(product_id: int, db: AsyncSession = Depends(get_async_db), current_user: UserModel = Depends(get_current_seller)):
    """
    Выполняет мягкое удаление товара, если он принадлежит текущему продавцу (только для 'seller').
    """
    # Проверяем, существует ли активный товар
    stmt = select(ProductModel).where(ProductModel.id == product_id, ProductModel.is_active == True)
    prod = await db.scalars(stmt)
    prod = prod.first()
    if prod is None:
        raise HTTPException(status_code=404, detail="Product not found or inactive")
    if prod.seller_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only delete your own products")

    # Изменяем объект установив is_active=False и сохраняем
    stmt = update(ProductModel).where(ProductModel.id == product_id).values(is_active=False)
    await db.execute(stmt)
    await db.commit()
    await db.refresh(prod)
    return prod