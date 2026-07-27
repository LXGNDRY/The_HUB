/**
 * lb-razorpay.js — Legendary Branding Razorpay cart checkout integration
 *
 * Wires the #lb-razorpay-upi-btn button (rendered by cart-summary.liquid)
 * to the lb-razorpay-backend Cloud Run service.
 *
 * Flow:
 *   1. Click → fetch /cart.js for line items
 *   2. Collect shipping address (customer default or inline form)
 *   3. POST GCP_BASE/create-order → Razorpay order_id
 *   4. Open Razorpay Standard Checkout modal
 *   5. On success → POST GCP_BASE/verify-payment → redirect to order status URL
 *   6. On failure → show inline error, re-enable button
 *
 * Config is injected via window.LB_RZP_CONFIG by cart-summary.liquid.
 */

(function () {
  'use strict';

  const cfg = window.LB_RZP_CONFIG || {};
  const GCP_BASE = (cfg.gcpBase || '').replace(/\/$/, '');
  const RZP_KEY  = cfg.rzpKey  || '';

  if (!GCP_BASE || !RZP_KEY) return; // settings not filled in yet

  // ── DOM refs ──────────────────────────────────────────────────────────────

  const btn     = document.getElementById('lb-razorpay-upi-btn');
  const wrapper = document.getElementById('lb-razorpay-upi-wrapper');
  if (!btn || !wrapper) return;

  // Error display
  const errEl = document.createElement('p');
  errEl.id = 'lb-rzp-error';
  errEl.style.cssText = 'color:#c0392b;font-size:0.85rem;margin:6px 0 0;display:none;';
  wrapper.appendChild(errEl);

  // ── Helpers ───────────────────────────────────────────────────────────────

  function showError(msg) {
    errEl.textContent = msg;
    errEl.style.display = 'block';
  }

  function clearError() {
    errEl.style.display = 'none';
    errEl.textContent = '';
  }

  function setLoading(loading) {
    btn.disabled = loading;
    btn.querySelector('span').textContent = loading ? 'Processing…' : cfg.btnLabel || 'Pay with Razorpay';
  }

  function loadRazorpayScript() {
    return new Promise((resolve, reject) => {
      if (window.Razorpay) { resolve(); return; }
      const s = document.createElement('script');
      s.src = 'https://checkout.razorpay.com/v1/checkout.js';
      s.onload = resolve;
      s.onerror = () => reject(new Error('Failed to load Razorpay checkout'));
      document.head.appendChild(s);
    });
  }

  async function fetchCart() {
    const resp = await fetch('/cart.js');
    if (!resp.ok) throw new Error('Could not read cart');
    return resp.json();
  }

  // ── Address collection ─────────────────────────────────────────────────────
  // Try Shopify customer default address first; for guests show a small form.

  function getCustomerAddress() {
    const ca = window.Shopify && window.Shopify.customerAddress;
    if (ca && ca.address1) {
      return Promise.resolve({
        first_name: ca.first_name || '',
        last_name:  ca.last_name  || '',
        address1:   ca.address1   || '',
        city:       ca.city       || '',
        province:   ca.province   || '',
        zip:        ca.zip        || '',
        country:    ca.country    || 'India',
        phone:      ca.phone      || ''
      });
    }
    return collectAddressFromForm();
  }

  function collectAddressFromForm() {
    return new Promise((resolve, reject) => {
      // Build a lightweight modal overlay
      const overlay = document.createElement('div');
      overlay.id = 'lb-rzp-addr-overlay';
      overlay.style.cssText = [
        'position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,.55);',
        'display:flex;align-items:center;justify-content:center;padding:16px;'
      ].join('');

      overlay.innerHTML = `
        <div style="background:#fff;border-radius:8px;padding:24px;width:100%;max-width:420px;font-family:inherit;">
          <h3 style="margin:0 0 16px;font-size:1.1rem;">Shipping address</h3>
          <form id="lb-rzp-addr-form">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
              <label style="display:flex;flex-direction:column;font-size:.85rem;gap:4px;">
                First name *
                <input name="first_name" required style="${inputStyle()}">
              </label>
              <label style="display:flex;flex-direction:column;font-size:.85rem;gap:4px;">
                Last name *
                <input name="last_name" required style="${inputStyle()}">
              </label>
            </div>
            <label style="display:flex;flex-direction:column;font-size:.85rem;gap:4px;margin-top:10px;">
              Address *
              <input name="address1" required style="${inputStyle()}">
            </label>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px;">
              <label style="display:flex;flex-direction:column;font-size:.85rem;gap:4px;">
                City *
                <input name="city" required style="${inputStyle()}">
              </label>
              <label style="display:flex;flex-direction:column;font-size:.85rem;gap:4px;">
                State *
                <input name="province" required style="${inputStyle()}">
              </label>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px;">
              <label style="display:flex;flex-direction:column;font-size:.85rem;gap:4px;">
                Pincode *
                <input name="zip" required inputmode="numeric" style="${inputStyle()}">
              </label>
              <label style="display:flex;flex-direction:column;font-size:.85rem;gap:4px;">
                Phone
                <input name="phone" inputmode="tel" style="${inputStyle()}">
              </label>
            </div>
            <div style="display:flex;gap:10px;margin-top:18px;">
              <button type="submit"
                style="flex:1;padding:10px;background:#000;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:.9rem;">
                Continue to Payment
              </button>
              <button type="button" id="lb-rzp-addr-cancel"
                style="padding:10px 16px;background:#f0f0f0;border:none;border-radius:4px;cursor:pointer;">
                Cancel
              </button>
            </div>
          </form>
        </div>`;

      document.body.appendChild(overlay);

      overlay.querySelector('#lb-rzp-addr-cancel').addEventListener('click', () => {
        overlay.remove();
        reject(new Error('cancelled'));
      });

      overlay.querySelector('#lb-rzp-addr-form').addEventListener('submit', (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        overlay.remove();
        resolve({
          first_name: fd.get('first_name'),
          last_name:  fd.get('last_name'),
          address1:   fd.get('address1'),
          city:       fd.get('city'),
          province:   fd.get('province'),
          zip:        fd.get('zip'),
          country:    'India',
          phone:      fd.get('phone') || ''
        });
      });
    });
  }

  function inputStyle() {
    return 'padding:8px;border:1px solid #ccc;border-radius:4px;font-size:.9rem;width:100%;box-sizing:border-box;';
  }

  // ── Main checkout handler ─────────────────────────────────────────────────

  btn.addEventListener('click', async () => {
    clearError();
    setLoading(true);

    try {
      // 1. Cart line items
      const cart = await fetchCart();
      const cartItems = cart.items.map(item => ({
        variant_id: item.variant_id,
        quantity:   item.quantity,
        price:      item.price
      }));
      if (!cartItems.length) {
        showError('Your cart is empty.');
        setLoading(false);
        return;
      }

      // 2. Customer info from button data attrs
      const customerEmail = btn.dataset.customerEmail || '';
      const customerName  = btn.dataset.customerName  || '';
      const cartTotal     = parseInt(btn.dataset.cartTotal,    10) || cart.total_price;
      const cartCurrency  = btn.dataset.cartCurrency  || 'USD';

      // 3. Shipping address
      let shippingAddress;
      try {
        shippingAddress = await getCustomerAddress();
      } catch (e) {
        // User cancelled address form
        setLoading(false);
        return;
      }

      // 4. Create Razorpay order on backend.
      // cart_items and shipping_address are stored in Razorpay order notes so
      // the webhook can reconstruct the Shopify order if this browser session
      // drops before /verify-payment is called.
      const orderResp = await fetch(`${GCP_BASE}/create-order`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          amount:           cartTotal,
          currency:         cartCurrency,
          customer_email:   customerEmail,
          customer_name:    customerName,
          cart_items:       cartItems,
          shipping_address: shippingAddress
        })
      });

      if (!orderResp.ok) {
        const err = await orderResp.json().catch(() => ({}));
        throw new Error(err.error || 'Could not create payment order. Please try again.');
      }

      const order = await orderResp.json();

      // 5. Load Razorpay SDK
      await loadRazorpayScript();

      // 6. Open Razorpay Standard Checkout
      const options = {
        key:       RZP_KEY,
        order_id:  order.id,
        amount:    order.amount,
        currency:  order.currency || 'INR',
        name:      'Legendary Branding',
        description: 'Order Payment',
        prefill: {
          email: customerEmail,
          name:  customerName
        },
        theme: { color: '#000000' },
        modal: {
          ondismiss: () => {
            setLoading(false);
          }
        },
        handler: async function (response) {
          // Payment captured by Razorpay — verify server-side and create Shopify order
          try {
            const verifyResp = await fetch(`${GCP_BASE}/verify-payment`, {
              method:  'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                razorpay_payment_id: response.razorpay_payment_id,
                razorpay_order_id:   response.razorpay_order_id,
                razorpay_signature:  response.razorpay_signature,
                cart_items:          cartItems,
                customer_email:      customerEmail,
                customer_name:       customerName,
                shipping_address:    shippingAddress
              })
            });

            const result = await verifyResp.json();

            if (result.success && result.order_status_url) {
              window.location.href = result.order_status_url;
            } else {
              throw new Error(result.error || 'Order confirmation failed. Please contact support.');
            }
          } catch (verifyErr) {
            showError(verifyErr.message || 'Payment received but order confirmation failed. Please contact support with your payment ID: ' + response.razorpay_payment_id);
            setLoading(false);
          }
        }
      };

      const rzp = new window.Razorpay(options);

      rzp.on('payment.failed', function (response) {
        const reason = response.error && response.error.description || 'Payment failed. Please try again.';
        showError(reason);
        setLoading(false);
      });

      rzp.open();

    } catch (err) {
      showError(err.message || 'Something went wrong. Please try again.');
      setLoading(false);
    }
  });

})();
