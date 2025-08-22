#!/usr/bin/env python3
"""
Seed Pizzatron database with dummy test data

This script populates the database with sample chefs, pizzas, images, and reviews
for testing purposes. Run this after the main database is initialized.
"""

from src.db import db_manager, Chef, Pizza, PizzaImage, ReviewCategory, PizzaReview, PizzaReviewScore

def seed_dummy_data():
    """Seed the database with dummy test data"""
    session = db_manager.get_session()
    try:
        print("Seeding dummy data...")
        
        # Check if we already have dummy data
        if session.query(Chef).count() > 0:
            print("Dummy data already exists. Clearing existing data...")
            # Clear existing data in proper order (respecting foreign keys)
            session.query(PizzaReviewScore).delete()
            session.query(PizzaReview).delete()
            session.query(PizzaImage).delete()
            session.query(Pizza).delete()
            session.query(Chef).delete()
            session.commit()
        
        # Create sample chefs
        chefs = [
            Chef(name="Mario Rossi", image_path="/images/chefs/mario.jpg"),
            Chef(name="Luigi Bianchi", image_path="/images/chefs/luigi.jpg"),
            Chef(name="Giuseppe Verde", image_path="/images/chefs/giuseppe.jpg"),
            Chef(name="Antonio Napoli", image_path="/images/chefs/antonio.jpg"),
        ]
        
        session.add_all(chefs)
        session.commit()
        print(f"Created {len(chefs)} dummy chefs")
        
        # Create sample pizzas
        pizzas = [
            Pizza(chef_id=1),  # Mario's pizzas
            Pizza(chef_id=1),
            Pizza(chef_id=2),  # Luigi's pizza
            Pizza(chef_id=3),  # Giuseppe's pizza
            Pizza(chef_id=4),  # Antonio's pizza
        ]
        
        session.add_all(pizzas)
        session.commit()
        print(f"Created {len(pizzas)} dummy pizzas")
        
        # Create sample pizza images
        pizza_images = [
            # Pizza 1 (Mario's first pizza)
            PizzaImage(pizza_id=1, image_path="/images/pizzas/margherita_1.jpg"),
            PizzaImage(pizza_id=1, image_path="/images/pizzas/margherita_2.jpg"),
            
            # Pizza 2 (Mario's second pizza)
            PizzaImage(pizza_id=2, image_path="/images/pizzas/pepperoni_1.jpg"),
            
            # Pizza 3 (Luigi's pizza)
            PizzaImage(pizza_id=3, image_path="/images/pizzas/quattro_stagioni.jpg"),
            
            # Pizza 4 (Giuseppe's pizza)
            PizzaImage(pizza_id=4, image_path="/images/pizzas/capricciosa.jpg"),
            
            # Pizza 5 (Antonio's pizza)
            PizzaImage(pizza_id=5, image_path="/images/pizzas/napoletana.jpg"),
        ]
        
        session.add_all(pizza_images)
        session.commit()
        print(f"Created {len(pizza_images)} dummy pizza images")
        
        # Get review categories
        categories = session.query(ReviewCategory).all()
        category_map = {cat.name: cat.id for cat in categories}
        
        # Create sample reviews with scores
        reviews_data = [
            {
                "pizza_id": 1,
                "summary": "ANALYSIS COMPLETE: Margherita shows acceptable roundness but crust execution is subpar. Cheese distribution exhibits minor irregularities. VERDICT: Mediocre attempt.",
                "scores": {"Roundness": 4, "Crust Quality": 3, "Topping Distribution": 3, "Color Appeal": 4, "Estimated Taste": 3, "Overall Presentation": 3}
            },
            {
                "pizza_id": 2,
                "summary": "PEPPERONI DETECTED: Circular formation adequate. Grease levels within acceptable parameters. However, pepperoni placement shows human inconsistency. DISAPPOINTING.",
                "scores": {"Roundness": 3, "Crust Quality": 4, "Topping Distribution": 2, "Color Appeal": 3, "Estimated Taste": 4, "Overall Presentation": 3}
            },
            {
                "pizza_id": 3,
                "summary": "QUATTRO STAGIONI ANALYSIS: Ambitious attempt detected. Multiple toppings create visual chaos but demonstrate culinary courage. Surprisingly competent execution.",
                "scores": {"Roundness": 4, "Crust Quality": 4, "Topping Distribution": 4, "Color Appeal": 5, "Estimated Taste": 4, "Overall Presentation": 4}
            },
            {
                "pizza_id": 4,
                "summary": "CAPRICCIOSA EVALUATION: Traditional approach noted. Execution meets baseline standards but lacks innovation. PIZZATRON expects more creativity.",
                "scores": {"Roundness": 3, "Crust Quality": 3, "Topping Distribution": 3, "Color Appeal": 3, "Estimated Taste": 3, "Overall Presentation": 3}
            },
            {
                "pizza_id": 5,
                "summary": "NAPOLETANA SPECIMEN: Excellent crust charring detected. Minimal toppings demonstrate confidence in fundamentals. IMPRESSIVE RESTRAINT. Well executed.",
                "scores": {"Roundness": 5, "Crust Quality": 5, "Topping Distribution": 5, "Color Appeal": 4, "Estimated Taste": 5, "Overall Presentation": 5}
            }
        ]
        
        for review_data in reviews_data:
            # Create pizza review
            pizza_review = PizzaReview(
                pizza_id=review_data["pizza_id"],
                review_summary=review_data["summary"]
            )
            session.add(pizza_review)
            session.commit()
            session.refresh(pizza_review)
            
            # Create scores for each category
            for category_name, score in review_data["scores"].items():
                if category_name in category_map:
                    score_record = PizzaReviewScore(
                        pizza_review_id=pizza_review.id,
                        category_id=category_map[category_name],
                        score=score
                    )
                    session.add(score_record)
            
            session.commit()
        
        print(f"Created {len(reviews_data)} dummy reviews with scores")
        print("Dummy data seeding completed successfully!")
        
    except Exception as e:
        session.rollback()
        print(f"Error seeding dummy data: {e}")
        raise
    finally:
        session.close()


def main():
    """Main function to run dummy data seeding"""
    print("=== PIZZATRON DUMMY DATA SEEDER ===")
    print("This will populate the database with test data for development.")
    
    # Initialize database first (creates tables and review categories)
    db_manager.initialize_database()
    
    # Add dummy data
    seed_dummy_data()
    
    print("\n=== SEEDING COMPLETE ===")
    print("Database now contains dummy chefs, pizzas, and reviews for testing.")


if __name__ == "__main__":
    main()