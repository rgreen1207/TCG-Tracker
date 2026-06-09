"""
SQLAlchemy ORM models — single SQLite file at data/tracker.db
"""
from __future__ import annotations
from datetime import datetime
from uuid import uuid4
from sqlalchemy import (
    Column, Integer, String, Float, Boolean,
    DateTime, ForeignKey, Text, UniqueConstraint, Index
)
from sqlalchemy.orm import DeclarativeBase, relationship


def _uuid() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


# ─────────────────────────────────────────────────────────────
# Sets & Products
# ─────────────────────────────────────────────────────────────

class PokemonSet(Base):
    __tablename__ = "sets"

    id           = Column(String(36), primary_key=True, default=_uuid)
    tcg_set_id   = Column(String(32), unique=True, nullable=True)   # pokemontcg.io id
    name_en      = Column(String(256), nullable=False)
    name_jp      = Column(String(256), nullable=True)
    set_code     = Column(String(16), nullable=True)
    series       = Column(String(128), nullable=True)
    release_date = Column(String(16), nullable=True)
    image_url    = Column(Text, nullable=True)
    is_japanese  = Column(Boolean, default=True)
    created_at   = Column(DateTime, default=datetime.utcnow)

    products = relationship("Product", back_populates="set", cascade="all, delete-orphan")
    cards    = relationship("Card", back_populates="set", cascade="all, delete-orphan")


class Product(Base):
    """Booster packs, booster boxes, special boxes, ETBs, gift sets, promo bundles."""
    __tablename__ = "products"

    id           = Column(String(36), primary_key=True, default=_uuid)
    set_id       = Column(String(36), ForeignKey("sets.id"), nullable=True)
    name_en      = Column(String(256), nullable=False)
    name_jp      = Column(String(256), nullable=True)
    product_type = Column(String(32), nullable=False)   # booster_pack | booster_box | special_box | etb | gift_set | promo
    msrp_jpy     = Column(Float, nullable=True)
    msrp_usd     = Column(Float, nullable=True)
    image_url    = Column(Text, nullable=True)
    notes        = Column(Text, nullable=True)
    is_active    = Column(Boolean, default=True)
    created_at   = Column(DateTime, default=datetime.utcnow)

    set              = relationship("PokemonSet", back_populates="products")
    price_history    = relationship("PriceHistory", back_populates="product",
                                    primaryjoin="and_(PriceHistory.item_type=='product', "
                                                "foreign(PriceHistory.item_id)==Product.id)",
                                    viewonly=True)


class Card(Base):
    """Individual cards — both Japanese and English."""
    __tablename__ = "cards"

    id          = Column(String(36), primary_key=True, default=_uuid)
    set_id      = Column(String(36), ForeignKey("sets.id"), nullable=True)
    tcg_card_id = Column(String(64), nullable=True)   # pokemontcg.io card id
    card_number = Column(String(16), nullable=True)
    name_en     = Column(String(256), nullable=False)
    name_jp     = Column(String(256), nullable=True)
    rarity      = Column(String(64), nullable=True)
    image_url   = Column(Text, nullable=True)
    is_japanese = Column(Boolean, default=True)
    created_at  = Column(DateTime, default=datetime.utcnow)

    set = relationship("PokemonSet", back_populates="cards")

    __table_args__ = (
        Index("idx_cards_name_en", "name_en"),
        Index("idx_cards_name_jp", "name_jp"),
    )


# ─────────────────────────────────────────────────────────────
# Price History
# ─────────────────────────────────────────────────────────────

class PriceHistory(Base):
    __tablename__ = "price_history"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    item_type      = Column(String(16), nullable=False)   # product | card
    item_id        = Column(String(36), nullable=False)
    source         = Column(String(64), nullable=False)   # eBay | PriceCharting | 130point
    price_usd      = Column(Float, nullable=True)
    price_jpy      = Column(Float, nullable=True)
    url            = Column(Text, nullable=True)
    title          = Column(Text, nullable=True)
    seller         = Column(String(128), nullable=True)
    seller_country = Column(String(8), nullable=True)
    grade          = Column(String(16), nullable=True)    # null = raw, "PSA 10" etc for graded
    ts             = Column(DateTime, default=datetime.utcnow, index=True)

    product = relationship(
        "Product",
        primaryjoin="and_(foreign(PriceHistory.item_type)=='product', "
                    "foreign(PriceHistory.item_id)==Product.id)",
        viewonly=True,
        uselist=False,
    )

    __table_args__ = (
        Index("idx_ph_item", "item_type", "item_id"),
        Index("idx_ph_ts",   "ts"),
    )


# ─────────────────────────────────────────────────────────────
# Collection
# ─────────────────────────────────────────────────────────────

class CollectionItem(Base):
    __tablename__ = "collection"

    id             = Column(String(36), primary_key=True, default=_uuid)
    item_type      = Column(String(16), nullable=False)   # product | card
    item_id        = Column(String(36), nullable=False)
    status         = Column(String(16), nullable=False)   # raw | graded
    grader         = Column(String(16), nullable=True)    # PSA | TAG
    grade          = Column(Float, nullable=True)         # 9.5, 10, etc.
    quantity       = Column(Integer, default=1)
    acquired_price_usd = Column(Float, nullable=True)
    acquired_date  = Column(String(16), nullable=True)
    notes          = Column(Text, nullable=True)
    created_at     = Column(DateTime, default=datetime.utcnow)
    updated_at     = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ─────────────────────────────────────────────────────────────
# Watchlist
# ─────────────────────────────────────────────────────────────

class WatchlistItem(Base):
    __tablename__ = "watchlist"

    id              = Column(String(36), primary_key=True, default=_uuid)
    item_type       = Column(String(16), nullable=False)
    item_id         = Column(String(36), nullable=False)
    target_price_usd = Column(Float, nullable=True)
    notes           = Column(Text, nullable=True)
    notified        = Column(Boolean, default=False)
    added_at        = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("item_type", "item_id", name="uq_watchlist_item"),
    )


# ─────────────────────────────────────────────────────────────
# Notifications config & alert log
# ─────────────────────────────────────────────────────────────

class NotificationConfig(Base):
    __tablename__ = "notification_config"

    id                  = Column(Integer, primary_key=True, default=1)
    enabled             = Column(Boolean, default=True)
    pushover_user_key   = Column(String(64), nullable=True)
    pushover_api_token  = Column(String(64), nullable=True)
    cooldown_hours      = Column(Float, default=12.0)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AlertLog(Base):
    __tablename__ = "alert_log"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    item_type  = Column(String(16), nullable=False)
    item_id    = Column(String(36), nullable=False)
    item_name  = Column(String(256), nullable=True)
    price_usd  = Column(Float, nullable=True)
    price_jpy  = Column(Float, nullable=True)
    url        = Column(Text, nullable=True)
    source     = Column(String(64), nullable=True)
    ts         = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────────────────────────
# FX rates cache
# ─────────────────────────────────────────────────────────────

class FxRate(Base):
    __tablename__ = "fx_rates"

    id       = Column(Integer, primary_key=True, autoincrement=True)
    ts       = Column(DateTime, default=datetime.utcnow)
    usd_jpy  = Column(Float, nullable=False)   # 1 USD = X JPY


# ─────────────────────────────────────────────────────────────
# Auth lockout
# ─────────────────────────────────────────────────────────────

class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    ip_address = Column(String(64), nullable=False, index=True)
    ts         = Column(DateTime, default=datetime.utcnow)
    success    = Column(Boolean, default=False)
