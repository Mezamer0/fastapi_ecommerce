from sqlalchemy import Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from datetime import datetime

class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"))
    comment: Mapped[int | bool] = mapped_column(Text, nullable=True)
    comment_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.now())
    grade: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    product: Mapped["Product"] = relationship('Product', back_populates='reviews')
    buyer: Mapped["User"] = relationship("User", back_populates="reviews")