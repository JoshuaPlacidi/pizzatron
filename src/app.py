#!/usr/bin/env python3
"""
Pizzatron FastAPI Web Application

A simple web interface for viewing and managing pizzas and chefs.
"""

from fastapi import FastAPI, Request, Depends, Form, UploadFile, File, BackgroundTasks
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from typing import List, Optional
import os
import uuid
from pathlib import Path
import asyncio

from .db import db_manager, init_db, Chef, Pizza, PizzaImage, ReviewCategory, PizzaReview, PizzaReviewScore
from .ai import generate_chef_image, review_pizza_images

# Initialize the database
init_db()

# Create FastAPI app
app = FastAPI(
    title="Pizzatron AI Judge",
    description="Retro AI system for analyzing pizza excellence at pizza making nights",
    version="1.0.0"
)

# Set up templates and static files
templates = Jinja2Templates(directory="src/templates")

# Create templates directory if it doesn't exist
os.makedirs("src/templates", exist_ok=True)
os.makedirs("src/static", exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory="src/static"), name="static")


def process_chef_image_background(chef_id: int, image_content: bytes, original_filename: str):
    """Background task to generate AI chef image and update database"""
    try:
        print(f"Starting AI image generation for chef {chef_id}...")
        
        # Generate the chef image with AI
        chef_image_bytes = generate_chef_image(image_content)
        
        # Create unique filename for generated image
        unique_filename = f"chef_ai_{uuid.uuid4().hex[:8]}.png"
        
        # Ensure chef images directory exists
        chef_images_dir = Path("src/static/images/chefs")
        chef_images_dir.mkdir(parents=True, exist_ok=True)
        
        # Save the generated image
        file_path = chef_images_dir / unique_filename
        with open(file_path, "wb") as f:
            f.write(chef_image_bytes)
        
        # Update the chef's image path in database
        ai_image_path = f"/static/images/chefs/{unique_filename}"
        
        # Update chef in database
        session = db_manager.get_session()
        try:
            chef = session.query(Chef).filter(Chef.id == chef_id).first()
            if chef:
                chef.image_path = ai_image_path
                session.commit()
                print(f"Successfully updated chef {chef_id} with AI image: {ai_image_path}")
            else:
                print(f"Chef {chef_id} not found for image update")
        except Exception as db_error:
            session.rollback()
            print(f"Database error updating chef image: {db_error}")
        finally:
            session.close()
            
    except Exception as e:
        print(f"Background AI generation failed for chef {chef_id}: {e}")
        # Keep the original uploaded image as fallback


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page showing all pizzas"""
    try:
        # Get all pizzas with their chef and images
        pizzas = db_manager.get_all_pizzas()
        chefs = db_manager.get_all_chefs()
        
        return templates.TemplateResponse(
            "index.html", 
            {
                "request": request,
                "pizzas": pizzas,
                "chefs": chefs,
                "title": "Pizzatron AI Judge - System Status"
            }
        )
    except Exception as e:
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "error": str(e),
                "title": "Error"
            }
        )


@app.get("/api/pizzas")
async def get_pizzas():
    """API endpoint to get all pizzas"""
    pizzas = db_manager.get_all_pizzas()
    return [
        {
            "id": pizza.id,
            "chef_id": pizza.chef_id,
            "chef_name": pizza.chef.name if pizza.chef else "Unknown",
            "created_at": pizza.created_at.isoformat(),
            "images": [
                {
                    "id": img.id,
                    "image_path": img.image_path,
                    "created_at": img.created_at.isoformat()
                }
                for img in pizza.images
            ]
        }
        for pizza in pizzas
    ]


@app.get("/api/chefs")
async def get_chefs():
    """API endpoint to get all chefs"""
    chefs = db_manager.get_all_chefs()
    return [
        {
            "id": chef.id,
            "name": chef.name,
            "image_path": chef.image_path,
            "created_at": chef.created_at.isoformat(),
            "pizza_count": len(chef.pizzas)
        }
        for chef in chefs
    ]


@app.get("/chef/{chef_id}", response_class=HTMLResponse)
async def chef_detail(request: Request, chef_id: int):
    """Chef detail page"""
    try:
        chef = db_manager.get_chef_with_pizzas(chef_id)
        if not chef:
            return templates.TemplateResponse(
                "error.html",
                {
                    "request": request,
                    "error": f"Chef with ID {chef_id} not found",
                    "title": "Chef Not Found"
                }
            )
        
        return templates.TemplateResponse(
            "chef_detail.html",
            {
                "request": request,
                "chef": chef,
                "title": f"Chef {chef.name}"
            }
        )
    except Exception as e:
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "error": str(e),
                "title": "Error"
            }
        )


@app.get("/create-chef", response_class=HTMLResponse)
async def create_chef_form(request: Request):
    """Create new chef form page"""
    return templates.TemplateResponse(
        "create_chef.html",
        {
            "request": request,
            "title": "Create New Chef"
        }
    )


@app.post("/create-chef")
async def create_chef_submit(
    request: Request, 
    background_tasks: BackgroundTasks,
    name: str = Form(...), 
    image: Optional[UploadFile] = File(None)
):
    """Handle chef creation form submission"""
    try:
        # Validate name
        if not name or len(name.strip()) == 0:
            return templates.TemplateResponse(
                "create_chef.html",
                {
                    "request": request,
                    "title": "Create New Chef",
                    "error": "Chef name is required",
                    "name": name
                }
            )
        
        # Handle image upload with background processing
        temp_image_path = None
        should_process_ai = False
        image_content = None
        
        if image and image.filename:
            # Validate file type
            allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
            file_extension = Path(image.filename).suffix.lower()
            
            if file_extension not in allowed_extensions:
                return templates.TemplateResponse(
                    "create_chef.html",
                    {
                        "request": request,
                        "title": "Create New Chef",
                        "error": "Invalid image format. Please use JPG, PNG, GIF, or WebP.",
                        "name": name
                    }
                )
            
            # Read the uploaded image bytes
            image_content = await image.read()
            
            # Save temporary original image immediately
            temp_filename = f"chef_temp_{uuid.uuid4().hex[:8]}{file_extension}"
            chef_images_dir = Path("src/static/images/chefs")
            chef_images_dir.mkdir(parents=True, exist_ok=True)
            
            temp_file_path = chef_images_dir / temp_filename
            with open(temp_file_path, "wb") as f:
                f.write(image_content)
            
            temp_image_path = f"/static/images/chefs/{temp_filename}"
            should_process_ai = True
        
        # Create the chef immediately with temporary image
        chef = db_manager.create_chef(
            name=name.strip(),
            image_path=temp_image_path
        )
        
        # Start background AI processing if needed
        if should_process_ai and image_content:
            background_tasks.add_task(
                process_chef_image_background, 
                chef.id, 
                image_content, 
                image.filename
            )
        
        # Redirect immediately to the new chef's page
        return RedirectResponse(url=f"/chef/{chef.id}", status_code=303)
        
    except Exception as e:
        return templates.TemplateResponse(
            "create_chef.html",
            {
                "request": request,
                "title": "Create New Chef",
                "error": f"Failed to create chef: {str(e)}",
                "name": name
            }
        )


@app.get("/submit-pizza", response_class=HTMLResponse)
async def submit_pizza_form(request: Request):
    """Pizza submission form page"""
    chefs = db_manager.get_all_chefs()
    return templates.TemplateResponse(
        "submit_pizza.html",
        {
            "request": request,
            "chefs": chefs,
            "title": "Submit Pizza for Judgment"
        }
    )


@app.post("/submit-pizza")
async def submit_pizza_handler(
    request: Request,
    background_tasks: BackgroundTasks,
    chef_id: int = Form(...),
    images: List[UploadFile] = File(...)
):
    """Handle pizza submission with AI review"""
    try:
        # Validate chef exists
        chef = db_manager.get_chef_by_id(chef_id)
        if not chef:
            chefs = db_manager.get_all_chefs()
            return templates.TemplateResponse(
                "submit_pizza.html",
                {
                    "request": request,
                    "chefs": chefs,
                    "error": "Invalid chef selected",
                    "title": "Submit Pizza for Judgment"
                }
            )
        
        # Validate image count
        if len(images) < 1 or len(images) > 3:
            chefs = db_manager.get_all_chefs()
            return templates.TemplateResponse(
                "submit_pizza.html",
                {
                    "request": request,
                    "chefs": chefs,
                    "selected_chef_id": chef_id,
                    "error": "Please upload 1-3 pizza images",
                    "title": "Submit Pizza for Judgment"
                }
            )
        
        # Validate file types
        allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
        for image in images:
            if image.filename:
                file_extension = Path(image.filename).suffix.lower()
                if file_extension not in allowed_extensions:
                    chefs = db_manager.get_all_chefs()
                    return templates.TemplateResponse(
                        "submit_pizza.html",
                        {
                            "request": request,
                            "chefs": chefs,
                            "selected_chef_id": chef_id,
                            "error": "Invalid image format. Please use JPG, PNG, GIF, or WebP.",
                            "title": "Submit Pizza for Judgment"
                        }
                    )
        
        # Create pizza record
        pizza = db_manager.create_pizza(chef_id)
        
        # Save pizza images
        pizza_image_paths = []
        pizza_images_dir = Path("src/static/images/pizzas")
        pizza_images_dir.mkdir(parents=True, exist_ok=True)
        
        for i, image in enumerate(images):
            if image.filename:
                file_extension = Path(image.filename).suffix.lower()
                unique_filename = f"pizza_{pizza.id}_{i+1}_{uuid.uuid4().hex[:8]}{file_extension}"
                
                image_content = await image.read()
                file_path = pizza_images_dir / unique_filename
                
                with open(file_path, "wb") as f:
                    f.write(image_content)
                
                web_path = f"/static/images/pizzas/{unique_filename}"
                pizza_image_paths.append(web_path)
                
                # Add to database
                db_manager.add_pizza_image(pizza.id, web_path)
        
        # Start background AI review
        background_tasks.add_task(
            process_pizza_review_background,
            pizza.id,
            pizza_image_paths,
            chef.name
        )
        
        # Redirect to pizza detail/results page
        return RedirectResponse(url=f"/pizza/{pizza.id}", status_code=303)
        
    except Exception as e:
        chefs = db_manager.get_all_chefs()
        return templates.TemplateResponse(
            "submit_pizza.html",
            {
                "request": request,
                "chefs": chefs,
                "error": f"Failed to submit pizza: {str(e)}",
                "title": "Submit Pizza for Judgment"
            }
        )


def process_pizza_review_background(pizza_id: int, image_paths: list, chef_name: str):
    """Background task to review pizza and save results"""
    try:
        print(f"Starting pizza review for pizza {pizza_id}...")
        
        # Get AI review
        review_data = review_pizza_images(image_paths, chef_name)
        
        # Save review to database
        session = db_manager.get_session()
        try:
            # Create pizza review
            pizza_review = PizzaReview(
                pizza_id=pizza_id,
                review_summary=review_data["review_summary"]
            )
            session.add(pizza_review)
            session.commit()
            session.refresh(pizza_review)
            
            # Get all categories
            categories = session.query(ReviewCategory).all()
            category_map = {cat.name: cat.id for cat in categories}
            
            # Save scores
            for category_name, score in review_data["scores"].items():
                if category_name in category_map:
                    score_record = PizzaReviewScore(
                        pizza_review_id=pizza_review.id,
                        category_id=category_map[category_name],
                        score=score
                    )
                    session.add(score_record)
            
            session.commit()
            print(f"Successfully saved review for pizza {pizza_id}")
            
        except Exception as db_error:
            session.rollback()
            print(f"Database error saving review: {db_error}")
        finally:
            session.close()
            
    except Exception as e:
        print(f"Background pizza review failed for pizza {pizza_id}: {e}")


@app.get("/pizza/{pizza_id}", response_class=HTMLResponse)
async def pizza_detail(request: Request, pizza_id: int):
    """Pizza detail and review page"""
    try:
        pizza = db_manager.get_pizza_with_images(pizza_id)
        if not pizza:
            return templates.TemplateResponse(
                "error.html",
                {
                    "request": request,
                    "error": f"Pizza with ID {pizza_id} not found",
                    "title": "Pizza Not Found"
                }
            )
        
        return templates.TemplateResponse(
            "pizza_detail.html",
            {
                "request": request,
                "pizza": pizza,
                "title": f"Pizza {pizza_id} Analysis"
            }
        )
    except Exception as e:
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "error": str(e),
                "title": "Error"
            }
        )


@app.get("/leaderboard", response_class=HTMLResponse)
async def leaderboard(request: Request):
    """Leaderboard page showing best pizzas"""
    try:
        # Get pizzas with reviews, ordered by average score
        session = db_manager.get_session()
        try:
            from sqlalchemy import func, distinct
            
            # Get pizza IDs with their average scores (simple aggregation)
            pizza_scores = (
                session.query(
                    Pizza.id,
                    func.avg(PizzaReviewScore.score).label('avg_score')
                )
                .select_from(Pizza)
                .join(PizzaReview, Pizza.id == PizzaReview.pizza_id)
                .join(PizzaReviewScore, PizzaReview.id == PizzaReviewScore.pizza_review_id)
                .group_by(Pizza.id)
                .order_by(func.avg(PizzaReviewScore.score).desc())
                .limit(10)
                .all()
            )
            
            # Convert to a list of tuples with pizza objects and scores
            pizzas_with_scores = []
            for pizza_id, avg_score in pizza_scores:
                pizza = session.query(Pizza).filter(Pizza.id == pizza_id).first()
                if pizza:
                    pizzas_with_scores.append((pizza, avg_score))
            
            return templates.TemplateResponse(
                "leaderboard.html",
                {
                    "request": request,
                    "pizzas_with_scores": pizzas_with_scores,
                    "title": "Pizza Leaderboard"
                }
            )
        finally:
            session.close()
            
    except Exception as e:
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "error": str(e),
                "title": "Error"
            }
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
