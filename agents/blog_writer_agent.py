"""
Blog Writer Agent
=================
Generates and publishes SEO-optimized blog articles to the Legendary Branding
Shopify store using Gemini AI. Designed to run 3x per day via the APScheduler,
publishing one article per run (3 posts/day).

Env vars:
  BLOG_SHOPIFY_BLOG_ID  — Shopify blog ID (auto-detected if unset)
  BLOG_POSTS_PER_RUN    — Articles per scheduler run (default 1)
  BLOG_AUTHOR           — Article author name (default "Legendary Branding")
"""

import os
import logging

from modules.gemini import GeminiModule
from modules.shopify import list_blogs, list_articles, create_article, update_article
from config import DRY_RUN

logger = logging.getLogger("gcp-bot.blog_writer")

BLOG_AUTHOR = os.getenv("BLOG_AUTHOR", "Legendary Branding")
BLOG_POSTS_PER_RUN = int(os.getenv("BLOG_POSTS_PER_RUN", "1"))
_BLOG_ID_ENV = os.getenv("BLOG_SHOPIFY_BLOG_ID", "")

# ---------------------------------------------------------------------------
# Curated topic list — 52 topics covering style guides, product deep-dives,
# streetwear culture, and SEO long-tail queries for broad organic traffic.
# ---------------------------------------------------------------------------
BLOG_TOPICS = [
    # Style guides
    {"topic": "How to Style a Heavyweight Hoodie for Every Season", "keywords": ["heavyweight hoodie", "streetwear hoodie", "oversized hoodie outfit"]},
    {"topic": "5 Outfit Ideas Built Around Premium Streetwear Basics", "keywords": ["streetwear basics", "premium streetwear outfits", "streetwear essentials"]},
    {"topic": "How to Layer Streetwear in Winter Without Losing Style", "keywords": ["streetwear winter layering", "oversized hoodie winter", "streetwear cold weather"]},
    {"topic": "How to Style Oversized Joggers for a Clean Streetwear Look", "keywords": ["oversized joggers outfit", "streetwear joggers", "premium jogger pants"]},
    {"topic": "The Ultimate Guide to Streetwear Color Palettes", "keywords": ["streetwear color palette", "neutral streetwear", "monochrome streetwear"]},
    {"topic": "How to Dress Up Streetwear for a Night Out", "keywords": ["streetwear night out", "elevated streetwear", "dress up hoodie"]},
    {"topic": "Capsule Wardrobe Essentials for Streetwear Fans", "keywords": ["streetwear capsule wardrobe", "streetwear wardrobe basics", "essential streetwear pieces"]},
    {"topic": "How to Wear a Heavyweight Crewneck: 5 Looks to Try", "keywords": ["heavyweight crewneck", "crewneck streetwear", "premium crewneck sweatshirt"]},
    {"topic": "Building a Monochrome Streetwear Outfit From Head to Toe", "keywords": ["monochrome streetwear", "all black streetwear", "tonal outfit ideas"]},
    {"topic": "How to Style Streetwear for Work Without Looking Casual", "keywords": ["smart casual streetwear", "streetwear office outfit", "elevated casual look"]},
    {"topic": "Best Streetwear Outfits for Fall 2025", "keywords": ["streetwear fall outfits", "fall streetwear 2025", "autumn streetwear looks"]},
    {"topic": "How to Mix High and Low Pieces in a Streetwear Outfit", "keywords": ["high low streetwear", "luxury streetwear mix", "affordable streetwear"]},
    {"topic": "Streetwear Outfit Formulas That Never Go Out of Style", "keywords": ["streetwear outfit formula", "timeless streetwear", "classic streetwear looks"]},
    {"topic": "How to Choose the Right Fit for Streetwear Pieces", "keywords": ["streetwear fit guide", "oversized vs regular fit", "streetwear sizing"]},
    {"topic": "Summer Streetwear: Staying Fresh When It Heats Up", "keywords": ["summer streetwear", "streetwear summer outfits", "lightweight streetwear"]},

    # Product deep-dives
    {"topic": "What Makes a 460GSM Hoodie Worth Every Penny", "keywords": ["460gsm hoodie", "heavyweight hoodie quality", "premium hoodie fabric"]},
    {"topic": "The Difference Between 280GSM and 460GSM Fleece Explained", "keywords": ["280gsm vs 460gsm", "hoodie fabric weight", "fleece gsm guide"]},
    {"topic": "Why Fabric Weight Matters in Streetwear", "keywords": ["fabric weight streetwear", "gsm clothing", "heavyweight vs lightweight fabric"]},
    {"topic": "How Premium Streetwear Is Made: From Cotton to Finished Garment", "keywords": ["how streetwear is made", "premium garment construction", "streetwear manufacturing"]},
    {"topic": "The Complete Guide to Caring for Heavyweight Fleece", "keywords": ["how to wash heavyweight hoodie", "fleece care guide", "hoodie care instructions"]},
    {"topic": "Drop Shoulder vs Regular Fit Hoodies: Which Is Right for You", "keywords": ["drop shoulder hoodie", "oversized hoodie fit", "hoodie fit guide"]},
    {"topic": "What to Look for When Buying a Premium Hoodie", "keywords": ["best premium hoodie", "hoodie buying guide", "quality hoodie features"]},
    {"topic": "The Anatomy of a Quality Streetwear Piece", "keywords": ["quality streetwear", "what makes streetwear premium", "streetwear construction"]},
    {"topic": "Why Heavyweight Cotton Is Dominating Streetwear in 2025", "keywords": ["heavyweight cotton streetwear", "heavyweight cotton hoodie 2025", "premium cotton streetwear"]},
    {"topic": "Preshrunk vs Unshrunk Cotton in Streetwear: What You Need to Know", "keywords": ["preshrunk cotton hoodie", "cotton shrinkage streetwear", "how to prevent hoodie shrinkage"]},

    # Streetwear culture
    {"topic": "The History of Streetwear: From Skate Culture to Luxury", "keywords": ["history of streetwear", "streetwear origins", "streetwear evolution"]},
    {"topic": "How Hip-Hop Shaped Streetwear as We Know It", "keywords": ["hip hop streetwear", "rap culture fashion", "hip hop fashion history"]},
    {"topic": "The Rise of Independent Streetwear Brands in the 2020s", "keywords": ["independent streetwear brands", "small streetwear brands", "best independent streetwear"]},
    {"topic": "Streetwear vs Athleisure: Where the Lines Blur", "keywords": ["streetwear vs athleisure", "streetwear athletic wear", "athleisure trend"]},
    {"topic": "How Social Media Changed the Streetwear Industry Forever", "keywords": ["streetwear social media", "Instagram streetwear", "streetwear influencers"]},
    {"topic": "Why Quality Over Hype Is the New Streetwear Movement", "keywords": ["quality over hype streetwear", "anti-hype streetwear", "understated streetwear"]},
    {"topic": "The Most Influential Streetwear Moments of the Last Decade", "keywords": ["streetwear history 2010s", "iconic streetwear moments", "streetwear milestones"]},
    {"topic": "How Streetwear Went Mainstream Without Losing Its Soul", "keywords": ["streetwear mainstream", "streetwear culture shift", "streetwear identity"]},
    {"topic": "The Role of Limited Drops in Streetwear Culture", "keywords": ["limited drop streetwear", "streetwear drop culture", "exclusive streetwear releases"]},
    {"topic": "Why Authenticity Is the Most Important Thing in Streetwear", "keywords": ["authentic streetwear", "streetwear authenticity", "real streetwear brand"]},

    # SEO long-tail
    {"topic": "Best Heavyweight Hoodies for Men in 2025", "keywords": ["best heavyweight hoodie men", "mens heavyweight hoodie 2025", "premium hoodie men"]},
    {"topic": "Best Heavyweight Hoodies for Women in 2025", "keywords": ["best heavyweight hoodie women", "womens heavyweight hoodie 2025", "premium hoodie women"]},
    {"topic": "Where to Buy Premium Streetwear Online Without the Markup", "keywords": ["buy premium streetwear online", "best streetwear websites", "affordable premium streetwear"]},
    {"topic": "Top 10 Streetwear Brands for Quality You Can Trust", "keywords": ["best quality streetwear brands", "top streetwear brands 2025", "premium streetwear brands"]},
    {"topic": "Best Oversized Hoodies for Streetwear Outfits in 2025", "keywords": ["best oversized hoodie 2025", "oversized hoodie streetwear", "popular oversized hoodies"]},
    {"topic": "How to Find Your Perfect Streetwear Aesthetic", "keywords": ["streetwear aesthetic", "find your streetwear style", "streetwear style guide"]},
    {"topic": "Streetwear Gift Guide: What to Buy the Hype Head in Your Life", "keywords": ["streetwear gift guide", "gifts for streetwear fans", "best streetwear gifts"]},
    {"topic": "Why Black Hoodies Are a Streetwear Staple Worth Investing In", "keywords": ["black hoodie streetwear", "best black hoodie", "black oversized hoodie"]},
    {"topic": "Best Neutral Streetwear Pieces for a Versatile Wardrobe", "keywords": ["neutral streetwear", "neutral hoodie", "versatile streetwear pieces"]},
    {"topic": "Streetwear on a Budget: How to Build a Premium-Looking Wardrobe", "keywords": ["streetwear budget", "affordable streetwear", "budget premium streetwear"]},
    {"topic": "How to Tell If a Streetwear Brand Actually Cares About Quality", "keywords": ["quality streetwear brand", "how to spot quality clothing", "premium vs cheap streetwear"]},
    {"topic": "The Best Streetwear Outfits You Can Build With Just 5 Pieces", "keywords": ["minimalist streetwear wardrobe", "5 piece streetwear", "simple streetwear outfits"]},
    {"topic": "Heavyweight Joggers: The Underrated Streetwear Staple of 2025", "keywords": ["heavyweight joggers", "premium joggers streetwear", "best heavyweight sweatpants"]},
    {"topic": "Why Chicago and the Midwest Are the New Streetwear Capitals", "keywords": ["Chicago streetwear", "Midwest streetwear scene", "Chicago fashion brands"]},
    {"topic": "Streetwear for Every Body Type: A Practical Style Guide", "keywords": ["streetwear body types", "streetwear all body types", "inclusive streetwear guide"]},
    {"topic": "The Psychology Behind Why We Love Streetwear", "keywords": ["why people love streetwear", "streetwear psychology", "streetwear identity and culture"]},
    {"topic": "How to Build Brand Loyalty in Streetwear: A Customer's Perspective", "keywords": ["streetwear brand loyalty", "best streetwear brands to follow", "loyal streetwear community"]},
]


def _get_blog_id() -> int:
    """Resolve blog ID from env var or auto-detect from first Shopify blog."""
    if _BLOG_ID_ENV:
        return int(_BLOG_ID_ENV)
    data = list_blogs()
    blogs = data.get("blogs", [])
    if not blogs:
        raise RuntimeError("No Shopify blogs found. Create a blog in Shopify admin first.")
    blog_id = blogs[0]["id"]
    logger.info("[blog_writer] Auto-detected blog_id: %d (%s)", blog_id, blogs[0].get("title", ""))
    return blog_id


def _get_published_titles(blog_id: int) -> set[str]:
    """Fetch recently published article titles for idempotency checking."""
    data = list_articles(blog_id, limit=50)
    articles = data.get("articles", [])
    return {a["title"].lower().strip() for a in articles}


def _pick_topics(published_titles: set[str], count: int) -> list[dict]:
    """Return up to `count` topics not already published."""
    picks = []
    for entry in BLOG_TOPICS:
        if len(picks) >= count:
            break
        if entry["topic"].lower().strip() not in published_titles:
            picks.append(entry)
    return picks


def run_blog_writer(blog_id: int = None, posts_per_run: int = None) -> dict:
    """
    Generate and publish blog posts to Shopify.

    Args:
        blog_id:       Shopify blog ID. Defaults to BLOG_SHOPIFY_BLOG_ID env var or auto-detect.
        posts_per_run: Number of articles to publish. Defaults to BLOG_POSTS_PER_RUN env var.

    Returns:
        {"published": [list of published titles], "skipped": [already live], "errors": [list of error strings]}
    """
    if posts_per_run is None:
        posts_per_run = BLOG_POSTS_PER_RUN

    result = {"published": [], "skipped": [], "errors": []}

    try:
        resolved_blog_id = blog_id or _get_blog_id()
    except Exception as e:
        result["errors"].append(f"Could not resolve blog_id: {e}")
        return result

    published_titles = _get_published_titles(resolved_blog_id)
    topics = _pick_topics(published_titles, posts_per_run)

    if not topics:
        logger.info("[blog_writer] All topics already published — nothing to do.")
        result["skipped"] = [t["topic"] for t in BLOG_TOPICS[:posts_per_run]]
        return result

    gemini = GeminiModule()

    for entry in topics:
        topic = entry["topic"]
        keywords = entry["keywords"]
        logger.info("[blog_writer] Generating post: %s", topic)

        try:
            post = gemini.generate_blog_post(topic, keywords)
        except Exception as e:
            logger.error("[blog_writer] Gemini generation failed for '%s': %s", topic, e)
            result["errors"].append(f"Generation failed — {topic}: {e}")
            continue

        title = post.get("title", topic)
        body_html = post.get("body_html", "")
        tags = post.get("tags", ", ".join(keywords))
        meta_title = post.get("meta_title", title[:60])
        meta_description = post.get("meta_description", "")

        if DRY_RUN:
            logger.info("[blog_writer] [DRY RUN] Would publish: %s", title)
            result["published"].append(f"[DRY RUN] {title}")
            continue

        try:
            article_data = create_article(
                blog_id=resolved_blog_id,
                title=title,
                body_html=body_html,
                author=BLOG_AUTHOR,
                tags=tags,
                published=True,
            )
            article_id = article_data["article"]["id"]
            logger.info("[blog_writer] Published article id=%d: %s", article_id, title)

            # Patch SEO meta via update_article
            update_article(resolved_blog_id, article_id, {
                "metafields_global_title_tag": meta_title,
                "metafields_global_description_tag": meta_description,
            })
            logger.info("[blog_writer] SEO meta patched for article id=%d", article_id)
            result["published"].append(title)

        except Exception as e:
            logger.error("[blog_writer] Shopify publish failed for '%s': %s", title, e)
            result["errors"].append(f"Publish failed — {title}: {e}")

    return result
