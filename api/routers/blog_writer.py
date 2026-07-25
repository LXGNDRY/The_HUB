"""
Blog Writer router — on-demand blog post generation and publishing.

Endpoints:
  POST /api/blog-writer/run     — generate and publish N blog posts immediately
  GET  /api/blog-writer/topics  — list all available topics in the rotation queue
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

logger = logging.getLogger("gcp-bot.api.blog_writer")
router = APIRouter()


class RunBlogWriterRequest(BaseModel):
    blog_id: Optional[int] = Field(None, description="Shopify blog ID (auto-detected if omitted)")
    posts_per_run: int = Field(1, ge=1, le=5, description="Number of articles to generate and publish (1-5)")


@router.post("/run")
def run_blog_writer_endpoint(req: RunBlogWriterRequest):
    """Generate and publish blog posts to Shopify immediately."""
    try:
        from agents.blog_writer_agent import run_blog_writer
        result = run_blog_writer(blog_id=req.blog_id, posts_per_run=req.posts_per_run)
        return result
    except Exception as e:
        logger.error("[blog_writer] /run failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/topics")
def list_topics():
    """List all topics in the blog writer rotation queue."""
    from agents.blog_writer_agent import BLOG_TOPICS
    return {"count": len(BLOG_TOPICS), "topics": BLOG_TOPICS}
