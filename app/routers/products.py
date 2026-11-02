from itertools import product

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db_depends import get_db
from app.schemas import Product as ProductSchema, ProductCreate
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


@router.get("/", response_model=list[ProductSchema], status_code=status.HTTP_200_OK)
async def get_all_products(db: AsyncSession = Depends(get_async_db)):
    """
    Возвращает список всех товаров.
    """
    stmt = select(ProductModel).join(CategoryModel).where(ProductModel.is_active == True,
                                                       CategoryModel.is_active == True,
                                                       ProductModel.stock > 0)
    res = await db.scalars(stmt)
    return res.all()


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