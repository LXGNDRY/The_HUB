"""
Legendary Branding — Build all 7 Klaviyo flow email templates
Brand Spec: White background | Black Bebas Neue | Black buttons / White text
"""

# ─── SHARED FOOTER ────────────────────────────────────────────────────────────
FOOTER = """
    <tr>
      <td style="background-color:#000000; padding:32px 40px; text-align:center;">
        <div style="font-family:'Bebas Neue','Arial Black',Impact,sans-serif; font-size:20px; letter-spacing:4px; color:#ffffff; margin-bottom:16px;">LEGENDARY BRANDING</div>
        <div style="margin-bottom:14px;">
          <a href="https://legendary-branding.com/collections/all" style="font-family:Arial,sans-serif; font-size:11px; color:#888888; text-decoration:none; letter-spacing:1px; text-transform:uppercase; margin:0 10px;">SHOP</a>
          <a href="https://legendary-branding.com/pages/contact" style="font-family:Arial,sans-serif; font-size:11px; color:#888888; text-decoration:none; letter-spacing:1px; text-transform:uppercase; margin:0 10px;">CONTACT</a>
          <a href="{{ unsubscribe_url }}" style="font-family:Arial,sans-serif; font-size:11px; color:#888888; text-decoration:none; letter-spacing:1px; text-transform:uppercase; margin:0 10px;">UNSUBSCRIBE</a>
        </div>
        <div style="font-family:Arial,sans-serif; font-size:11px; color:#555555; line-height:1.6; margin-bottom:12px;">Legendary Branding &bull; Lake Forest, IL</div>
        <div><a href="{{ unsubscribe_url }}" style="font-family:Arial,sans-serif; font-size:11px; color:#555555; text-decoration:underline;">Unsubscribe from all marketing emails</a></div>
      </td>
    </tr>
"""

def wrap(preview: str, body_rows: str) -> str:
    """Wrap body rows in full HTML email shell."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<!--[if mso]><noscript><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml></noscript><![endif]-->
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Inter:wght@400;500&display=swap');
body{{margin:0;padding:0;background:#ffffff;-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;}}
table{{border-collapse:collapse;}}
@media only screen and (max-width:620px){{
  .mob-pad{{padding:28px 20px !important;}}
  .mob-heading{{font-size:34px !important;}}
  .mob-btn{{padding:14px 28px !important;}}
  .mob-hide{{display:none !important;}}
}}
</style>
</head>
<body style="margin:0;padding:0;background:#ffffff;">
<span style="display:none;max-height:0;overflow:hidden;">{preview}&#847;&zwnj;&#847;&zwnj;&#847;&zwnj;&#847;&zwnj;&#847;&zwnj;&#847;&zwnj;&#847;&zwnj;&#847;&zwnj;&#847;&zwnj;&#847;&zwnj;</span>
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#ffffff;">
  <tr><td align="center" style="padding:0;">
    <table width="600" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;width:100%;background:#ffffff;">
      <!-- HEADER -->
      <tr>
        <td style="background:#000000;padding:26px 40px;text-align:center;">
          <a href="https://legendary-branding.com" style="font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:30px;color:#ffffff;letter-spacing:4px;text-decoration:none;">LEGENDARY BRANDING</a>
        </td>
      </tr>
      {body_rows}
      {FOOTER}
    </table>
  </td></tr>
</table>
</body>
</html>"""


# ─── 1. WELCOME SERIES ────────────────────────────────────────────────────────
def welcome_series_email_1():
    body = """
      <!-- HERO -->
      <tr>
        <td class="mob-pad" style="padding:48px 40px 32px;text-align:center;border-bottom:1px solid #ebebeb;">
          <div style="font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:12px;letter-spacing:3px;color:#999999;text-transform:uppercase;margin-bottom:10px;">Welcome to the Family</div>
          <div class="mob-heading" style="font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:52px;line-height:1.0;color:#000000;letter-spacing:2px;margin-bottom:16px;">YOU'RE<br>LEGENDARY NOW</div>
          <div style="font-family:Arial,sans-serif;font-size:15px;line-height:1.7;color:#444444;max-width:460px;margin:0 auto;">Welcome, {{ first_name|default:"" }}. You just joined a brand built on quality, culture, and identity. Here's your exclusive welcome offer.</div>
        </td>
      </tr>
      <!-- DISCOUNT -->
      <tr>
        <td style="background:#000000;padding:28px 40px;text-align:center;">
          <div style="font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:12px;letter-spacing:3px;color:#888888;text-transform:uppercase;margin-bottom:10px;">Your Welcome Discount</div>
          <div style="font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:42px;letter-spacing:6px;color:#ffffff;">{{ coupon.code|default:"LEGENDARY10" }}</div>
          <div style="font-family:Arial,sans-serif;font-size:12px;color:#666666;margin-top:8px;letter-spacing:1px;">10% OFF YOUR FIRST ORDER &bull; EXPIRES IN 48 HOURS</div>
        </td>
      </tr>
      <!-- BODY -->
      <tr>
        <td class="mob-pad" style="padding:40px 40px;">
          <p style="font-family:Arial,sans-serif;font-size:15px;line-height:1.7;color:#333333;margin:0 0 20px;">We don't do fast fashion. Every piece from Legendary Branding is designed to stand out, built to last, and made to represent the culture.</p>
          <p style="font-family:Arial,sans-serif;font-size:15px;line-height:1.7;color:#333333;margin:0 0 32px;">Use your code above and start building your collection today.</p>
          <div style="text-align:center;">
            <a href="https://legendary-branding.com/collections/all" class="mob-btn" style="display:inline-block;background:#000000;color:#ffffff;font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:16px;letter-spacing:3px;text-decoration:none;padding:16px 48px;border:2px solid #000000;">SHOP THE COLLECTION</a>
          </div>
        </td>
      </tr>
      <!-- DIVIDER -->
      <tr><td style="height:1px;background:#ebebeb;"></td></tr>
    """
    return wrap("Welcome — here's 10% off your first order.", body)


# ─── 2. CUSTOMER THANK YOU ────────────────────────────────────────────────────
def customer_thank_you():
    body = """
      <!-- HERO -->
      <tr>
        <td class="mob-pad" style="padding:48px 40px 32px;text-align:center;border-bottom:1px solid #ebebeb;">
          <div style="font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:12px;letter-spacing:3px;color:#999999;text-transform:uppercase;margin-bottom:10px;">Order Confirmed</div>
          <div class="mob-heading" style="font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:52px;line-height:1.0;color:#000000;letter-spacing:2px;margin-bottom:16px;">THANK YOU,<br>{{ first_name|default:"" }}</div>
          <div style="font-family:Arial,sans-serif;font-size:15px;line-height:1.7;color:#444444;max-width:460px;margin:0 auto;">Your order has been received and is being processed. We'll send you a shipping confirmation as soon as it's on its way.</div>
        </td>
      </tr>
      <!-- ORDER SUMMARY -->
      <tr>
        <td class="mob-pad" style="padding:40px 40px;">
          <div style="border:1px solid #000000;padding:24px;">
            <div style="font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:11px;letter-spacing:3px;color:#999999;text-transform:uppercase;margin-bottom:16px;">Order Summary</div>
            <div style="display:table;width:100%;">
              <div style="font-family:Arial,sans-serif;font-size:13px;color:#333333;line-height:1.8;">
                <strong style="font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:14px;letter-spacing:1px;color:#000000;">ORDER #{{ event.extra.order_number|default:"——" }}</strong>
              </div>
            </div>
            <div style="height:1px;background:#ebebeb;margin:16px 0;"></div>
            {% for item in event.extra.line_items %}
            <div style="font-family:Arial,sans-serif;font-size:14px;color:#333333;line-height:1.8;display:flex;justify-content:space-between;">
              <span>{{ item.title }} &times; {{ item.quantity }}</span>
              <span>${{ item.price }}</span>
            </div>
            {% endfor %}
            <div style="height:1px;background:#ebebeb;margin:16px 0;"></div>
            <div style="font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:16px;letter-spacing:1px;color:#000000;text-align:right;">TOTAL: ${{ event.extra.total_price|default:"——" }}</div>
          </div>
          <div style="text-align:center;margin-top:32px;">
            <a href="https://legendary-branding.com/collections/all" class="mob-btn" style="display:inline-block;background:#000000;color:#ffffff;font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:16px;letter-spacing:3px;text-decoration:none;padding:16px 48px;border:2px solid #000000;">CONTINUE SHOPPING</a>
          </div>
        </td>
      </tr>
      <!-- DIVIDER -->
      <tr><td style="height:1px;background:#ebebeb;"></td></tr>
    """
    return wrap("Your order is confirmed — thank you for your purchase.", body)


# ─── 3. ABANDONED CART ────────────────────────────────────────────────────────
def abandoned_cart():
    body = """
      <!-- HERO -->
      <tr>
        <td class="mob-pad" style="padding:48px 40px 32px;text-align:center;border-bottom:1px solid #ebebeb;">
          <div style="font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:12px;letter-spacing:3px;color:#999999;text-transform:uppercase;margin-bottom:10px;">Don't Sleep On It</div>
          <div class="mob-heading" style="font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:52px;line-height:1.0;color:#000000;letter-spacing:2px;margin-bottom:16px;">YOUR CART<br>IS WAITING</div>
          <div style="font-family:Arial,sans-serif;font-size:15px;line-height:1.7;color:#444444;max-width:460px;margin:0 auto;">You left something behind. These pieces move fast — don't miss your chance to secure the look.</div>
        </td>
      </tr>
      <!-- CART ITEMS -->
      <tr>
        <td class="mob-pad" style="padding:40px 40px;">
          <div style="font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:11px;letter-spacing:3px;color:#999999;text-transform:uppercase;margin-bottom:20px;">Left in Your Cart</div>
          {% for item in event.extra.line_items %}
          <div style="display:table;width:100%;border:1px solid #ebebeb;margin-bottom:12px;">
            <div style="display:table-cell;width:80px;vertical-align:top;padding:12px;">
              {% if item.image_url %}<img src="{{ item.image_url }}" width="80" height="80" alt="{{ item.title }}" style="display:block;object-fit:cover;">{% endif %}
            </div>
            <div style="display:table-cell;vertical-align:top;padding:12px;">
              <div style="font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:16px;letter-spacing:1px;color:#000000;">{{ item.title }}</div>
              {% if item.variant_title %}<div style="font-family:Arial,sans-serif;font-size:12px;color:#888888;margin-top:2px;">{{ item.variant_title }}</div>{% endif %}
              <div style="font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:14px;color:#000000;margin-top:6px;">${{ item.price }}</div>
            </div>
          </div>
          {% endfor %}
          <div style="text-align:center;margin-top:32px;">
            <a href="{{ event.extra.checkout_url|default:'https://legendary-branding.com/cart' }}" class="mob-btn" style="display:inline-block;background:#000000;color:#ffffff;font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:16px;letter-spacing:3px;text-decoration:none;padding:16px 48px;border:2px solid #000000;">COMPLETE YOUR ORDER</a>
          </div>
        </td>
      </tr>
      <!-- URGENCY -->
      <tr>
        <td style="background:#000000;padding:20px 40px;text-align:center;">
          <div style="font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:13px;letter-spacing:3px;color:#888888;text-transform:uppercase;">Limited Stock &bull; Don't Miss Out</div>
        </td>
      </tr>
      <!-- DIVIDER -->
      <tr><td style="height:1px;background:#ebebeb;"></td></tr>
    """
    return wrap("You left items in your cart — they won't last long.", body)


# ─── 4. BROWSE ABANDONMENT ───────────────────────────────────────────────────
def browse_abandonment():
    body = """
      <!-- HERO -->
      <tr>
        <td class="mob-pad" style="padding:48px 40px 32px;text-align:center;border-bottom:1px solid #ebebeb;">
          <div style="font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:12px;letter-spacing:3px;color:#999999;text-transform:uppercase;margin-bottom:10px;">Still Thinking?</div>
          <div class="mob-heading" style="font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:52px;line-height:1.0;color:#000000;letter-spacing:2px;margin-bottom:16px;">YOU WERE<br>LOOKING AT THIS</div>
          <div style="font-family:Arial,sans-serif;font-size:15px;line-height:1.7;color:#444444;max-width:460px;margin:0 auto;">We noticed you checking out some of our pieces. These drops don't stick around — here's what caught your eye.</div>
        </td>
      </tr>
      <!-- BROWSED PRODUCT -->
      <tr>
        <td class="mob-pad" style="padding:40px 40px;text-align:center;">
          {% if event.extra.item.image_url %}
          <img src="{{ event.extra.item.image_url }}" width="280" alt="{{ event.extra.item.title }}" style="display:inline-block;max-width:100%;margin-bottom:20px;">
          {% endif %}
          <div style="font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:24px;letter-spacing:2px;color:#000000;margin-bottom:8px;">{{ event.extra.item.title }}</div>
          <div style="font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:20px;color:#000000;margin-bottom:28px;">${{ event.extra.item.price }}</div>
          <a href="{{ event.extra.item.url|default:'https://legendary-branding.com/collections/all' }}" class="mob-btn" style="display:inline-block;background:#000000;color:#ffffff;font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:16px;letter-spacing:3px;text-decoration:none;padding:16px 48px;border:2px solid #000000;">GET IT NOW</a>
        </td>
      </tr>
      <!-- DIVIDER -->
      <tr><td style="height:1px;background:#ebebeb;"></td></tr>
    """
    return wrap("You were looking at something — it's still available.", body)


# ─── 5. SHIPPING CONFIRMATION ────────────────────────────────────────────────
def shipping_confirmation():
    body = """
      <!-- HERO -->
      <tr>
        <td class="mob-pad" style="padding:48px 40px 32px;text-align:center;border-bottom:1px solid #ebebeb;">
          <div style="font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:12px;letter-spacing:3px;color:#999999;text-transform:uppercase;margin-bottom:10px;">It's On Its Way</div>
          <div class="mob-heading" style="font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:52px;line-height:1.0;color:#000000;letter-spacing:2px;margin-bottom:16px;">YOUR ORDER<br>HAS SHIPPED</div>
          <div style="font-family:Arial,sans-serif;font-size:15px;line-height:1.7;color:#444444;max-width:460px;margin:0 auto;">Your package is packed and in transit. Track it in real time with the link below.</div>
        </td>
      </tr>
      <!-- SHIPPING DETAILS -->
      <tr>
        <td class="mob-pad" style="padding:40px 40px;">
          <div style="border:1px solid #000000;padding:24px;margin-bottom:28px;">
            <div style="font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:11px;letter-spacing:3px;color:#999999;text-transform:uppercase;margin-bottom:16px;">Shipment Details</div>
            <div style="margin-bottom:12px;">
              <div style="font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:12px;letter-spacing:2px;color:#999999;text-transform:uppercase;">ORDER</div>
              <div style="font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:18px;color:#000000;">#{{ event.extra.order_number|default:"——" }}</div>
            </div>
            <div style="height:1px;background:#ebebeb;margin:12px 0;"></div>
            <div style="margin-bottom:12px;">
              <div style="font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:12px;letter-spacing:2px;color:#999999;text-transform:uppercase;">Tracking Number</div>
              <div style="font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:18px;color:#000000;">{{ event.extra.tracking_number|default:"——" }}</div>
              <div style="font-family:Arial,sans-serif;font-size:12px;color:#888888;margin-top:2px;">via {{ event.extra.shipping_service|default:"Carrier" }}</div>
            </div>
            <div style="height:1px;background:#ebebeb;margin:12px 0;"></div>
            <div>
              <div style="font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:12px;letter-spacing:2px;color:#999999;text-transform:uppercase;">Shipping To</div>
              <div style="font-family:Arial,sans-serif;font-size:14px;color:#333333;margin-top:4px;line-height:1.6;">{{ event.extra.shipping_address.first_name|default:"" }} {{ event.extra.shipping_address.last_name|default:"" }}<br>{{ event.extra.shipping_address.address1|default:"" }}<br>{{ event.extra.shipping_address.city|default:"" }}, {{ event.extra.shipping_address.province_code|default:"" }} {{ event.extra.shipping_address.zip|default:"" }}</div>
            </div>
          </div>
          <div style="text-align:center;">
            <a href="{{ event.extra.tracking_url|default:'https://legendary-branding.com' }}" class="mob-btn" style="display:inline-block;background:#000000;color:#ffffff;font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:16px;letter-spacing:3px;text-decoration:none;padding:16px 48px;border:2px solid #000000;">TRACK YOUR ORDER</a>
          </div>
        </td>
      </tr>
      <!-- DIVIDER -->
      <tr><td style="height:1px;background:#ebebeb;"></td></tr>
    """
    return wrap("Your Legendary Branding order has shipped — track it here.", body)


# ─── 6. OUT FOR DELIVERY ─────────────────────────────────────────────────────
def out_for_delivery():
    body = """
      <!-- HERO -->
      <tr>
        <td class="mob-pad" style="padding:48px 40px 32px;text-align:center;border-bottom:1px solid #ebebeb;">
          <div style="font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:12px;letter-spacing:3px;color:#999999;text-transform:uppercase;margin-bottom:10px;">Almost There</div>
          <div class="mob-heading" style="font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:52px;line-height:1.0;color:#000000;letter-spacing:2px;margin-bottom:16px;">OUT FOR<br>DELIVERY TODAY</div>
          <div style="font-family:Arial,sans-serif;font-size:15px;line-height:1.7;color:#444444;max-width:460px;margin:0 auto;">Your order is out for delivery. Expect it at your door today — make sure someone's available to receive it.</div>
        </td>
      </tr>
      <!-- STATUS BAR -->
      <tr>
        <td class="mob-pad" style="padding:32px 40px;">
          <table width="100%" cellpadding="0" cellspacing="0" border="0">
            <tr>
              <td style="text-align:center;padding:16px 4px;border-top:3px solid #000000;font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:11px;letter-spacing:2px;color:#000000;text-transform:uppercase;width:25%;">Ordered</td>
              <td style="text-align:center;padding:16px 4px;border-top:3px solid #000000;font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:11px;letter-spacing:2px;color:#000000;text-transform:uppercase;width:25%;">Shipped</td>
              <td style="text-align:center;padding:16px 4px;border-top:3px solid #000000;font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:11px;letter-spacing:2px;color:#000000;text-transform:uppercase;width:25%;">Out for Delivery</td>
              <td style="text-align:center;padding:16px 4px;border-top:3px solid #ebebeb;font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:11px;letter-spacing:2px;color:#bbbbbb;text-transform:uppercase;width:25%;">Delivered</td>
            </tr>
          </table>
        </td>
      </tr>
      <!-- DETAILS -->
      <tr>
        <td class="mob-pad" style="padding:0 40px 40px;text-align:center;">
          <p style="font-family:Arial,sans-serif;font-size:15px;line-height:1.7;color:#333333;margin:0 0 28px;">Order <strong>#{{ event.extra.order_number|default:"——" }}</strong> is on its way. Track real-time updates with the button below.</p>
          <a href="{{ event.extra.tracking_url|default:'https://legendary-branding.com' }}" class="mob-btn" style="display:inline-block;background:#000000;color:#ffffff;font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:16px;letter-spacing:3px;text-decoration:none;padding:16px 48px;border:2px solid #000000;">TRACK DELIVERY</a>
        </td>
      </tr>
      <!-- DIVIDER -->
      <tr><td style="height:1px;background:#ebebeb;"></td></tr>
    """
    return wrap("Your order is out for delivery — expect it today.", body)


# ─── 7. DELIVERED + REVIEW REQUEST ──────────────────────────────────────────
def delivered_review():
    body = """
      <!-- HERO -->
      <tr>
        <td class="mob-pad" style="padding:48px 40px 32px;text-align:center;border-bottom:1px solid #ebebeb;">
          <div style="font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:12px;letter-spacing:3px;color:#999999;text-transform:uppercase;margin-bottom:10px;">Delivered</div>
          <div class="mob-heading" style="font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:52px;line-height:1.0;color:#000000;letter-spacing:2px;margin-bottom:16px;">YOUR PACKAGE<br>HAS ARRIVED</div>
          <div style="font-family:Arial,sans-serif;font-size:15px;line-height:1.7;color:#444444;max-width:460px;margin:0 auto;">Order #{{ event.extra.order_number|default:"" }} has been delivered. We hope you love what you got — let us know what you think.</div>
        </td>
      </tr>
      <!-- BODY -->
      <tr>
        <td class="mob-pad" style="padding:40px 40px;text-align:center;">
          <p style="font-family:Arial,sans-serif;font-size:15px;line-height:1.7;color:#333333;margin:0 0 12px;">Real reviews from real people matter. If you're feeling the drip, take 60 seconds to leave us a review — it helps the brand grow and helps other customers know what's good.</p>
          <p style="font-family:Arial,sans-serif;font-size:15px;line-height:1.7;color:#333333;margin:0 0 32px;">And if anything's off, just hit reply — we make it right, every time.</p>
          <a href="https://legendary-branding.com/pages/reviews" class="mob-btn" style="display:inline-block;background:#000000;color:#ffffff;font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:16px;letter-spacing:3px;text-decoration:none;padding:16px 48px;border:2px solid #000000;">LEAVE A REVIEW</a>
        </td>
      </tr>
      <!-- BACK TO SHOP -->
      <tr>
        <td style="background:#000000;padding:24px 40px;text-align:center;">
          <div style="font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:12px;letter-spacing:3px;color:#888888;text-transform:uppercase;margin-bottom:12px;">Keep Building Your Collection</div>
          <a href="https://legendary-branding.com/collections/all" style="display:inline-block;background:#ffffff;color:#000000;font-family:'Bebas Neue','Arial Black',Impact,sans-serif;font-size:15px;letter-spacing:3px;text-decoration:none;padding:14px 40px;border:2px solid #ffffff;">SHOP NEW ARRIVALS</a>
        </td>
      </tr>
      <!-- DIVIDER -->
      <tr><td style="height:1px;background:#ebebeb;"></td></tr>
    """
    return wrap("Your order arrived — how are you liking it?", body)


# ─── BUILD ALL ────────────────────────────────────────────────────────────────
TEMPLATES = {
    "LB — Welcome Series Email 1": welcome_series_email_1(),
    "LB — Customer Thank You":     customer_thank_you(),
    "LB — Abandoned Cart":         abandoned_cart(),
    "LB — Browse Abandonment":     browse_abandonment(),
    "LB — Shipping Confirmation":  shipping_confirmation(),
    "LB — Out for Delivery":       out_for_delivery(),
    "LB — Delivered + Review":     delivered_review(),
}

if __name__ == "__main__":
    import os
    out_dir = "/home/user/workspace/klaviyo_templates/output"
    os.makedirs(out_dir, exist_ok=True)
    for name, html in TEMPLATES.items():
        fname = name.lower().replace(" ", "_").replace("—", "").replace("__", "_").strip("_") + ".html"
        path = os.path.join(out_dir, fname)
        with open(path, "w") as f:
            f.write(html)
        print(f"✓ Built: {path} ({len(html):,} chars)")
    print(f"\nAll {len(TEMPLATES)} templates built.")
