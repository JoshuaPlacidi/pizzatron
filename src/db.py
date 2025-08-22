import os
from datetime import datetime
from typing import List, Optional
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session, joinedload
from dotenv import load_dotenv

load_dotenv()

Base = declarative_base()


class Chef(Base):
    __tablename__ = 'chefs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    image_path = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship to pizzas
    pizzas = relationship("Pizza", back_populates="chef", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Chef(id={self.id}, name='{self.name}')>"


class Pizza(Base):
    __tablename__ = 'pizzas'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    chef_id = Column(Integer, ForeignKey('chefs.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    chef = relationship("Chef", back_populates="pizzas")
    images = relationship("PizzaImage", back_populates="pizza", cascade="all, delete-orphan")
    review = relationship("PizzaReview", back_populates="pizza", uselist=False, cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Pizza(id={self.id}, chef_id={self.chef_id})>"


class PizzaImage(Base):
    __tablename__ = 'pizza_images'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    pizza_id = Column(Integer, ForeignKey('pizzas.id'), nullable=False)
    image_path = Column(String(500), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    pizza = relationship("Pizza", back_populates="images")
    
    def __repr__(self):
        return f"<PizzaImage(id={self.id}, pizza_id={self.pizza_id}, image_path='{self.image_path}')>"


class ReviewCategory(Base):
    __tablename__ = 'review_categories'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    
    # Relationship
    scores = relationship("PizzaReviewScore", back_populates="category", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<ReviewCategory(id={self.id}, name='{self.name}')>"


class PizzaReview(Base):
    __tablename__ = 'pizza_review'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    pizza_id = Column(Integer, ForeignKey('pizzas.id'), nullable=False)
    review_summary = Column(String(1000), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    pizza = relationship("Pizza", back_populates="review")
    scores = relationship("PizzaReviewScore", back_populates="review", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<PizzaReview(id={self.id}, pizza_id={self.pizza_id})>"


class PizzaReviewScore(Base):
    __tablename__ = 'pizza_review_scores'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    pizza_review_id = Column(Integer, ForeignKey('pizza_review.id'), nullable=False)
    category_id = Column(Integer, ForeignKey('review_categories.id'), nullable=False)
    score = Column(Integer, nullable=False)  # 1-5 scale
    
    # Relationships
    review = relationship("PizzaReview", back_populates="scores")
    category = relationship("ReviewCategory", back_populates="scores")
    
    def __repr__(self):
        return f"<PizzaReviewScore(review_id={self.pizza_review_id}, category_id={self.category_id}, score={self.score})>"


class DatabaseManager:
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.getenv("DB_PATH", "pizzatron.db")
        
        self.db_path = db_path
        self.engine = create_engine(f'sqlite:///{db_path}')
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        
    def create_tables(self):
        """Create all tables if they don't exist"""
        Base.metadata.create_all(bind=self.engine)
        
    def get_session(self) -> Session:
        """Get a database session"""
        return self.SessionLocal()
    
    def seed_database(self):
        """Seed the database with review categories only"""
        session = self.get_session()
        try:
            # Check if review categories already exist
            if session.query(ReviewCategory).count() > 0:
                print("Review categories already exist, skipping seed.")
                return
                
            # Create review categories (only essential data)
            categories = [
                ReviewCategory(name="Shape"),
                ReviewCategory(name="Crust Quality"),
                ReviewCategory(name="Presentation"),
                ReviewCategory(name="Bake Quality"),
                ReviewCategory(name="Flavor (estimated)"),
                ReviewCategory(name="Overall")
            ]
            
            session.add_all(categories)
            session.commit()
            
            print("Review categories seeded successfully!")
            
        except Exception as e:
            session.rollback()
            print(f"Error seeding review categories: {e}")
            raise
        finally:
            session.close()
    
    def initialize_database(self):
        """Initialize the database by creating tables and seeding if needed"""
        self.create_tables()
        self.seed_database()
    
    # Query methods for chefs
    def get_all_chefs(self) -> List[Chef]:
        """Get all chefs"""
        session = self.get_session()
        try:
            return session.query(Chef).options(
                joinedload(Chef.pizzas).joinedload(Pizza.images)
            ).all()
        finally:
            session.close()
    
    def get_chef_by_id(self, chef_id: int) -> Optional[Chef]:
        """Get a chef by ID"""
        session = self.get_session()
        try:
            return session.query(Chef).filter(Chef.id == chef_id).first()
        finally:
            session.close()
    
    def create_chef(self, name: str, image_path: str = None) -> Chef:
        """Create a new chef"""
        session = self.get_session()
        try:
            chef = Chef(name=name, image_path=image_path)
            session.add(chef)
            session.commit()
            session.refresh(chef)
            return chef
        except Exception as e:
            session.rollback()
            raise
        finally:
            session.close()
    
    # Query methods for pizzas
    def get_all_pizzas(self) -> List[Pizza]:
        """Get all pizzas with their chef information and reviews"""
        session = self.get_session()
        try:
            return session.query(Pizza).options(
                joinedload(Pizza.chef),
                joinedload(Pizza.images),
                joinedload(Pizza.review).joinedload(PizzaReview.scores).joinedload(PizzaReviewScore.category)
            ).all()
        finally:
            session.close()
    
    def get_pizzas_by_chef(self, chef_id: int) -> List[Pizza]:
        """Get all pizzas by a specific chef with reviews"""
        session = self.get_session()
        try:
            return session.query(Pizza).options(
                joinedload(Pizza.chef),
                joinedload(Pizza.images),
                joinedload(Pizza.review).joinedload(PizzaReview.scores).joinedload(PizzaReviewScore.category)
            ).filter(Pizza.chef_id == chef_id).all()
        finally:
            session.close()
    
    def create_pizza(self, chef_id: int) -> Pizza:
        """Create a new pizza"""
        session = self.get_session()
        try:
            pizza = Pizza(chef_id=chef_id)
            session.add(pizza)
            session.commit()
            session.refresh(pizza)
            return pizza
        except Exception as e:
            session.rollback()
            raise
        finally:
            session.close()
    
    # Query methods for pizza images
    def get_pizza_images(self, pizza_id: int) -> List[PizzaImage]:
        """Get all images for a specific pizza"""
        session = self.get_session()
        try:
            return session.query(PizzaImage).filter(PizzaImage.pizza_id == pizza_id).all()
        finally:
            session.close()
    
    def add_pizza_image(self, pizza_id: int, image_path: str) -> PizzaImage:
        """Add an image to a pizza"""
        session = self.get_session()
        try:
            pizza_image = PizzaImage(pizza_id=pizza_id, image_path=image_path)
            session.add(pizza_image)
            session.commit()
            session.refresh(pizza_image)
            return pizza_image
        except Exception as e:
            session.rollback()
            raise
        finally:
            session.close()
    
    # Complex queries
    def get_chef_with_pizzas(self, chef_id: int) -> Optional[Chef]:
        """Get a chef with all their pizzas and pizza images"""
        session = self.get_session()
        try:
            return session.query(Chef).options(
                joinedload(Chef.pizzas).joinedload(Pizza.images)
            ).filter(Chef.id == chef_id).first()
        finally:
            session.close()
    
    def get_pizza_with_images(self, pizza_id: int) -> Optional[Pizza]:
        """Get a pizza with all its images and review"""
        session = self.get_session()
        try:
            return session.query(Pizza).options(
                joinedload(Pizza.chef),
                joinedload(Pizza.images),
                joinedload(Pizza.review).joinedload(PizzaReview.scores).joinedload(PizzaReviewScore.category)
            ).filter(Pizza.id == pizza_id).first()
        finally:
            session.close()


# Global database manager instance
db_manager = DatabaseManager()

# Convenience functions for easy access
def init_db():
    """Initialize the database"""
    db_manager.initialize_database()

def get_db_session():
    """Get a database session for custom queries"""
    return db_manager.get_session()