import json
import urllib.parse
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, abort
from database import get_db, get_setting, generate_order_number

def format_price(amount):
    """Format price as Jordanian Dinar with 2 decimal places."""
    if amount is None:
        return ''
    try:
        val = float(amount)
        return f"{val:.2f} د.أ"
    except (ValueError, TypeError):
        return str(amount)

store_bp = Blueprint('store', __name__)

@store_bp.route('/')
def index():
    """Luxury Homepage for Waqar Men's Fashion."""
    conn = get_db()

    # 1. Categories for grid
    categories = conn.execute(
        "SELECT * FROM categories WHERE is_active = 1 ORDER BY display_order ASC"
    ).fetchall()

    # 2. New Arrivals (وصل حديثاً)
    new_arrivals = conn.execute('''
        SELECT p.*, c.name as category_name,
               (SELECT image_url FROM product_images WHERE product_id = p.id ORDER BY is_primary DESC, sort_order ASC LIMIT 1) as primary_image,
               (SELECT GROUP_CONCAT(DISTINCT color_hex) FROM product_variants WHERE product_id = p.id) as colors_hex,
               (SELECT GROUP_CONCAT(DISTINCT size_name) FROM product_variants WHERE product_id = p.id) as sizes_list,
               (SELECT SUM(stock_quantity) FROM product_variants WHERE product_id = p.id) as total_stock
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        WHERE p.is_published = 1 AND p.is_new = 1
        ORDER BY p.id DESC LIMIT 8
    ''').fetchall()

    # 3. Best Sellers (الأكثر مبيعاً)
    best_sellers = conn.execute('''
        SELECT p.*, c.name as category_name,
               (SELECT image_url FROM product_images WHERE product_id = p.id ORDER BY is_primary DESC, sort_order ASC LIMIT 1) as primary_image,
               (SELECT GROUP_CONCAT(DISTINCT color_hex) FROM product_variants WHERE product_id = p.id) as colors_hex,
               (SELECT GROUP_CONCAT(DISTINCT size_name) FROM product_variants WHERE product_id = p.id) as sizes_list,
               (SELECT SUM(stock_quantity) FROM product_variants WHERE product_id = p.id) as total_stock
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        WHERE p.is_published = 1 AND p.is_bestseller = 1
        ORDER BY p.id DESC LIMIT 8
    ''').fetchall()

    # 4. Offers (عروض وَقّار)
    offers = conn.execute('''
        SELECT p.*, c.name as category_name,
               (SELECT image_url FROM product_images WHERE product_id = p.id ORDER BY is_primary DESC, sort_order ASC LIMIT 1) as primary_image,
               (SELECT GROUP_CONCAT(DISTINCT color_hex) FROM product_variants WHERE product_id = p.id) as colors_hex,
               (SELECT GROUP_CONCAT(DISTINCT size_name) FROM product_variants WHERE product_id = p.id) as sizes_list,
               (SELECT SUM(stock_quantity) FROM product_variants WHERE product_id = p.id) as total_stock
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        WHERE p.is_published = 1 AND (p.is_offer = 1 OR p.discount_price IS NOT NULL)
        ORDER BY p.id DESC LIMIT 8
    ''').fetchall()

    # 5. Featured Products
    featured = conn.execute('''
        SELECT p.*, c.name as category_name,
               (SELECT image_url FROM product_images WHERE product_id = p.id ORDER BY is_primary DESC, sort_order ASC LIMIT 1) as primary_image,
               (SELECT GROUP_CONCAT(DISTINCT color_hex) FROM product_variants WHERE product_id = p.id) as colors_hex,
               (SELECT GROUP_CONCAT(DISTINCT size_name) FROM product_variants WHERE product_id = p.id) as sizes_list,
               (SELECT SUM(stock_quantity) FROM product_variants WHERE product_id = p.id) as total_stock
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        WHERE p.is_published = 1 AND p.is_featured = 1
        ORDER BY p.id DESC LIMIT 8
    ''').fetchall()

    conn.close()

    return render_template(
        'index.html',
        categories=categories,
        new_arrivals=new_arrivals,
        best_sellers=best_sellers,
        offers=offers,
        featured=featured
    )

@store_bp.route('/shop')
def shop():
    """Shop Page with multi-faceted filtering, sorting, and responsive grid."""
    conn = get_db()
    
    # Query parameters
    category_slug = request.args.get('category', '').strip()
    search_query = request.args.get('q', '').strip()
    filter_type = request.args.get('filter', '').strip() # new, best, offer
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    selected_size = request.args.get('size', '').strip()
    selected_color = request.args.get('color', '').strip()
    in_stock_only = request.args.get('in_stock', '').strip() == '1'
    sort_by = request.args.get('sort', 'newest').strip()

    # Build SQL Query
    query = '''
        SELECT DISTINCT p.*, c.name as category_name, c.slug as category_slug,
               (SELECT image_url FROM product_images WHERE product_id = p.id ORDER BY is_primary DESC, sort_order ASC LIMIT 1) as primary_image,
               (SELECT GROUP_CONCAT(DISTINCT color_hex) FROM product_variants WHERE product_id = p.id) as colors_hex,
               (SELECT GROUP_CONCAT(DISTINCT size_name) FROM product_variants WHERE product_id = p.id) as sizes_list,
               (SELECT SUM(stock_quantity) FROM product_variants WHERE product_id = p.id) as total_stock
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        LEFT JOIN product_variants pv ON pv.product_id = p.id
        WHERE p.is_published = 1
    '''
    params = []

    if category_slug:
        query += " AND c.slug = ?"
        params.append(category_slug)

    if search_query:
        query += " AND (p.name LIKE ? OR p.description LIKE ? OR c.name LIKE ? OR p.material LIKE ?)"
        term = f"%{search_query}%"
        params.extend([term, term, term, term])

    if filter_type == 'new':
        query += " AND p.is_new = 1"
    elif filter_type == 'best':
        query += " AND p.is_bestseller = 1"
    elif filter_type == 'offer':
        query += " AND (p.is_offer = 1 OR p.discount_price IS NOT NULL)"

    if min_price is not None:
        query += " AND COALESCE(p.discount_price, p.base_price) >= ?"
        params.append(min_price)

    if max_price is not None:
        query += " AND COALESCE(p.discount_price, p.base_price) <= ?"
        params.append(max_price)

    if selected_size:
        query += " AND pv.size_name = ?"
        params.append(selected_size)

    if selected_color:
        query += " AND (pv.color_name = ? OR pv.color_hex = ?)"
        params.extend([selected_color, selected_color])

    if in_stock_only:
        query += " AND (SELECT SUM(stock_quantity) FROM product_variants WHERE product_id = p.id) > 0"

    # Sorting
    if sort_by == 'price_asc':
        query += " ORDER BY COALESCE(p.discount_price, p.base_price) ASC"
    elif sort_by == 'price_desc':
        query += " ORDER BY COALESCE(p.discount_price, p.base_price) DESC"
    elif sort_by == 'bestseller':
        query += " ORDER BY p.is_bestseller DESC, p.views_count DESC"
    else: # newest default
        query += " ORDER BY p.id DESC"

    products = conn.execute(query, params).fetchall()

    # Get available filter options for sidebar
    categories = conn.execute("SELECT * FROM categories WHERE is_active = 1 ORDER BY display_order ASC").fetchall()
    all_sizes = conn.execute("SELECT DISTINCT size_name FROM product_variants WHERE size_name IS NOT NULL AND size_name != ''").fetchall()
    all_colors = conn.execute("SELECT DISTINCT color_name, color_hex FROM product_variants WHERE color_name IS NOT NULL").fetchall()

    conn.close()

    return render_template(
        'shop.html',
        products=products,
        categories=categories,
        all_sizes=all_sizes,
        all_colors=all_colors,
        current_category=category_slug,
        search_query=search_query,
        filter_type=filter_type,
        min_price=min_price,
        max_price=max_price,
        selected_size=selected_size,
        selected_color=selected_color,
        in_stock_only=in_stock_only,
        sort_by=sort_by
    )

@store_bp.route('/category/<slug>')
def category_view(slug):
    """Direct route for category."""
    return redirect(url_for('store.shop', category=slug))

@store_bp.route('/product/<slug>')
def product_detail(slug):
    """Product Details Page with images gallery, color/size matrix stock check, reviews, and related products."""
    conn = get_db()
    
    # 1. Fetch Product
    product = conn.execute('''
        SELECT p.*, c.name as category_name, c.slug as category_slug
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        WHERE p.slug = ? AND p.is_published = 1
    ''', (slug,)).fetchone()

    if not product:
        conn.close()
        abort(404)

    # Increment view count
    conn.execute("UPDATE products SET views_count = views_count + 1 WHERE id = ?", (product['id'],))
    conn.commit()

    # 2. Product Images
    images = conn.execute('''
        SELECT * FROM product_images
        WHERE product_id = ?
        ORDER BY is_primary DESC, sort_order ASC
    ''', (product['id'],)).fetchall()

    # 3. Product Variants (Color x Size matrix with stock)
    variants = conn.execute('''
        SELECT * FROM product_variants
        WHERE product_id = ?
        ORDER BY id ASC
    ''', (product['id'],)).fetchall()

    # Group colors and sizes
    colors = {}
    for v in variants:
        c_name = v['color_name']
        if c_name not in colors:
            colors[c_name] = {
                'name': c_name,
                'hex': v['color_hex'],
                'sizes': []
            }
        colors[c_name]['sizes'].append({
            'size': v['size_name'],
            'stock': v['stock_quantity'],
            'variant_id': v['id']
        })

    # 4. Approved Reviews
    reviews = conn.execute('''
        SELECT * FROM product_reviews
        WHERE product_id = ? AND is_approved = 1
        ORDER BY created_at DESC
    ''', (product['id'],)).fetchall()

    # Calculate average rating
    avg_rating = 0
    if reviews:
        avg_rating = round(sum(r['rating'] for r in reviews) / len(reviews), 1)

    # 5. Related Products (Same category, excluding current)
    related_products = conn.execute('''
        SELECT p.*, c.name as category_name,
               (SELECT image_url FROM product_images WHERE product_id = p.id ORDER BY is_primary DESC, sort_order ASC LIMIT 1) as primary_image,
               (SELECT GROUP_CONCAT(DISTINCT color_hex) FROM product_variants WHERE product_id = p.id) as colors_hex,
               (SELECT GROUP_CONCAT(DISTINCT size_name) FROM product_variants WHERE product_id = p.id) as sizes_list,
               (SELECT SUM(stock_quantity) FROM product_variants WHERE product_id = p.id) as total_stock
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        WHERE p.is_published = 1 AND p.category_id = ? AND p.id != ?
        ORDER BY p.id DESC LIMIT 4
    ''', (product['category_id'], product['id'])).fetchall()

    conn.close()

    # Variants JSON for live JS interactions
    variants_json = [
        {
            'id': v['id'],
            'color_name': v['color_name'],
            'color_hex': v['color_hex'],
            'size_name': v['size_name'],
            'stock': v['stock_quantity']
        } for v in variants
    ]

    return render_template(
        'product_detail.html',
        product=product,
        images=images,
        variants=variants,
        colors=colors,
        variants_json=json.dumps(variants_json, ensure_ascii=False),
        reviews=reviews,
        avg_rating=avg_rating,
        related_products=related_products
    )

@store_bp.route('/cart')
def cart_page():
    """Shopping Cart Page."""
    cart = session.get('cart', {})
    cart_items = []
    subtotal = 0.0

    conn = get_db()
    for key, item in cart.items():
        prod = conn.execute('''
            SELECT p.*,
                   (SELECT image_url FROM product_images WHERE product_id = p.id ORDER BY is_primary DESC, sort_order ASC LIMIT 1) as primary_image
            FROM products p WHERE p.id = ?
        ''', (item['product_id'],)).fetchone()

        if prod:
            # Check current variant stock
            var_row = conn.execute('''
                SELECT stock_quantity FROM product_variants
                WHERE product_id = ? AND color_name = ? AND size_name = ?
            ''', (item['product_id'], item['color'], item['size'])).fetchone()
            current_stock = var_row['stock_quantity'] if var_row else 0

            price = float(prod['discount_price'] or prod['base_price'])
            item_total = price * item['quantity']
            subtotal += item_total

            cart_items.append({
                'key': key,
                'product_id': prod['id'],
                'name': prod['name'],
                'slug': prod['slug'],
                'image': prod['primary_image'] or '/static/images/placeholder.svg',
                'color': item['color'],
                'size': item['size'],
                'price': price,
                'quantity': item['quantity'],
                'item_total': item_total,
                'stock': current_stock
            })

    # Fetch active delivery zones
    delivery_zones = conn.execute(
        "SELECT * FROM delivery_zones WHERE is_active = 1 ORDER BY id ASC"
    ).fetchall()

    conn.close()

    # Calculate discount from applied coupon if any
    coupon_data = session.get('applied_coupon')
    discount_amount = 0.0
    if coupon_data:
        if coupon_data['discount_type'] == 'percent':
            discount_amount = subtotal * (coupon_data['discount_value'] / 100.0)
        else:
            discount_amount = min(coupon_data['discount_value'], subtotal)

    # Free delivery threshold check
    free_delivery_threshold = float(get_setting('free_delivery_threshold', '50'))

    return render_template(
        'cart.html',
        cart_items=cart_items,
        subtotal=subtotal,
        discount_amount=discount_amount,
        applied_coupon=coupon_data,
        delivery_zones=delivery_zones,
        free_delivery_threshold=free_delivery_threshold
    )

@store_bp.route('/checkout', methods=['GET', 'POST'])
def checkout():
    """Checkout Page with Cash on Delivery and Order Confirmation."""
    cart = session.get('cart', {})
    if not cart:
        flash('سلة التسوق فارغة، يرجى إضافة منتجات أولاً.', 'warning')
        return redirect(url_for('store.shop'))

    conn = get_db()
    
    # 1. Fetch Cart Products & Calculate totals
    cart_items = []
    subtotal = 0.0
    has_out_of_stock = False

    for key, item in list(cart.items()):
        prod = conn.execute(
            "SELECT p.*, (SELECT image_url FROM product_images WHERE product_id = p.id ORDER BY is_primary DESC, sort_order ASC LIMIT 1) as primary_image FROM products p WHERE p.id = ? AND p.is_published = 1",
            (item['product_id'],)
        ).fetchone()

        if not prod:
            continue

        var_row = conn.execute(
            "SELECT stock_quantity FROM product_variants WHERE product_id = ? AND color_name = ? AND size_name = ?",
            (item['product_id'], item['color'], item['size'])
        ).fetchone()

        current_stock = var_row['stock_quantity'] if var_row else 0
        if current_stock < item['quantity']:
            has_out_of_stock = True

        price = float(prod['discount_price'] or prod['base_price'])
        item_total = price * item['quantity']
        subtotal += item_total

        cart_items.append({
            'product_id': prod['id'],
            'name': prod['name'],
            'image': prod['primary_image'] or '/static/images/placeholder.svg',
            'color': item['color'],
            'size': item['size'],
            'price': price,
            'quantity': item['quantity'],
            'item_total': item_total,
            'stock': current_stock
        })

    # Fetch active delivery zones
    delivery_zones = conn.execute(
        "SELECT * FROM delivery_zones WHERE is_active = 1 ORDER BY id ASC"
    ).fetchall()

    # Calculate discount
    coupon_data = session.get('applied_coupon')
    discount_amount = 0.0
    if coupon_data:
        if coupon_data['discount_type'] == 'percent':
            discount_amount = subtotal * (coupon_data['discount_value'] / 100.0)
        else:
            discount_amount = min(coupon_data['discount_value'], subtotal)

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        phone = request.form.get('phone', '').strip()
        governorate_id = request.form.get('governorate_id', type=int)
        city = request.form.get('city', '').strip()
        address = request.form.get('address', '').strip()
        notes = request.form.get('notes', '').strip()

        # Validation
        if not full_name or not phone or not governorate_id or not address:
            flash('يرجى ملء جميع الحقول المطلوبة لتأكيد طلبك.', 'danger')
            conn.close()
            return redirect(url_for('store.checkout'))

        # Phone check for Jordanian format (e.g. 079..., 078..., 077...)
        clean_phone = phone.replace(' ', '').replace('-', '').replace('+962', '0')
        if not (clean_phone.startswith('07') and len(clean_phone) == 10 and clean_phone.isdigit()):
            flash('يرجى إدخال رقم هاتف أردني صحيح (مثال: 0796667505).', 'danger')
            conn.close()
            return redirect(url_for('store.checkout'))

        # Check stock again before finalizing
        for item in cart_items:
            var_row = conn.execute(
                "SELECT stock_quantity FROM product_variants WHERE product_id = ? AND color_name = ? AND size_name = ?",
                (item['product_id'], item['color'], item['size'])
            ).fetchone()
            
            if not var_row or var_row['stock_quantity'] < item['quantity']:
                flash(f"عذراً، المقاس {item['size']} واللون {item['color']} من {item['name']} غير متوفر بالكمية المطلوبة.", 'danger')
                conn.close()
                return redirect(url_for('store.cart_page'))

        # Delivery zone fee
        zone = conn.execute(
            "SELECT * FROM delivery_zones WHERE id = ?",
            (governorate_id,)
        ).fetchone()
        delivery_fee = float(zone['fee']) if zone else 2.0
        gov_name = zone['governorate_name'] if zone else 'السلط'

        # Check free delivery threshold
        free_thresh = float(get_setting('free_delivery_threshold', '50'))
        if subtotal >= free_thresh:
            delivery_fee = 0.0

        total_amount = max(0.0, (subtotal - discount_amount)) + delivery_fee
        order_number = generate_order_number()

        # Customer identification or registration
        customer_id = session.get('customer_user', {}).get('id')
        if not customer_id:
            cust_row = conn.execute(
                "SELECT id FROM customers WHERE phone = ?",
                (clean_phone,)
            ).fetchone()
            if cust_row:
                customer_id = cust_row['id']
            else:
                cust_cur = conn.cursor()
                cust_cur.execute(
                    "INSERT INTO customers (name, phone, governorate, city, address) VALUES (?, ?, ?, ?, ?)",
                    (full_name, clean_phone, gov_name, city, address)
                )
                customer_id = cust_cur.lastrowid

        # Insert Order
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO orders (order_number, customer_id, customer_name, customer_phone, customer_governorate, customer_city, customer_address, notes, subtotal, discount_amount, coupon_code, delivery_fee, total_amount, payment_method, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                order_number, customer_id, full_name, clean_phone,
                gov_name, city, address, notes,
                subtotal, discount_amount, coupon_data['code'] if coupon_data else None,
                delivery_fee, total_amount, 'cash_on_delivery', 'new'
            )
        )
        order_id = cursor.lastrowid

        # Insert Order Items & Deduct Inventory Stock
        for item in cart_items:
            cursor.execute(
                "INSERT INTO order_items (order_id, product_id, product_name, color_name, size_name, unit_price, quantity, total_price, product_image) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    order_id,
                    item['product_id'],
                    item['name'],
                    item['color'],
                    item['size'],
                    item['price'],
                    item['quantity'],
                    item['item_total'],
                    item['image']
                )
            )

            # Deduct stock
            cursor.execute(
                "UPDATE product_variants SET stock_quantity = MAX(0, stock_quantity - ?) WHERE product_id = ? AND color_name = ? AND size_name = ?",
                (item['quantity'], item['product_id'], item['color'], item['size'])
            )

        # Update coupon usage count if used
        if coupon_data:
            cursor.execute(
                "UPDATE coupons SET used_count = used_count + 1 WHERE code = ?",
                (coupon_data['code'],)
            )

        # Fetch order items from database
        items = cursor.execute(
            "SELECT * FROM order_items WHERE order_id = ?",
            (order_id,)
        ).fetchall()
        
        conn.commit()
        conn.close()

        # Clear session cart and coupon
        session.pop('cart', None)
        session.pop('applied_coupon', None)

        # Send order details to WhatsApp
        whatsapp_num = get_setting('whatsapp', '+962796667505').replace('+', '').replace(' ', '')

        # Build detailed WhatsApp message
        wa_message = f"طلب جديد من متجر وَقّار#{order_number}%0A%0A"
        wa_message += f"العميل: {full_name}%0A"
        wa_message += f"الهاتف: {clean_phone}%0A"
        wa_message += f"المحافظة: {gov_name}%0A"
        wa_message += f"المدينة: {city}%0A"
        wa_message += f"العنوان: {address}%0A"

        if notes:
            wa_message += f"ملاحظات العميل: {notes}%0A"

        wa_message += f"%0Aالمنتجات:%0A"

        for item in cart_items:
            wa_message += f"- {item['name']} ({item['color']}، مقاس {item['size']}) × {item['quantity']} = {format_price(item['item_total'])}%0A"

        wa_message += f"%0Aالمجموع الفرعي: {format_price(subtotal)}%0A"

        if discount_amount > 0:
            wa_message += f"الخصم: {format_price(discount_amount)}%0A"

        wa_message += f"رسوم التوصيل: {format_price(delivery_fee)}%0A"
        wa_message += f"المجموع الكلي: {format_price(total_amount)}%0A"
        wa_message += f"%0Aيرجى تأكيد الطلب وتجهيزه للتوصيل."

        whatsapp_url = f"https://wa.me/{whatsapp_num}?text={wa_message}"

        # Create order dictionary for template
        order = {
            'order_number': order_number,
            'customer_name': full_name,
            'customer_phone': clean_phone,
            'customer_governorate': gov_name,
            'customer_city': city,
            'customer_address': address,
            'notes': notes,
            'subtotal': subtotal,
            'discount_amount': discount_amount,
            'delivery_fee': delivery_fee,
            'total_amount': total_amount
        }

        # Redirect directly to WhatsApp for immediate communication
        return redirect(whatsapp_url)

    conn.close()
    return render_template(
        'checkout.html',
        cart_items=cart_items,
        subtotal=subtotal,
        discount_amount=discount_amount,
        applied_coupon=coupon_data,
        delivery_zones=delivery_zones,
        has_out_of_stock=has_out_of_stock
    )

@store_bp.route('/order-confirmation/<order_number>')
def order_confirmation(order_number):
    """Order Success Confirmation Page."""
    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE order_number = ?", (order_number,)).fetchone()
    
    if not order:
        conn.close()
        abort(404)

    items = conn.execute("SELECT * FROM order_items WHERE order_id = ?", (order['id'],)).fetchall()
    conn.close()

    # Prepare prefilled WhatsApp message
    whatsapp_num = get_setting('whatsapp', '+962796667505').replace('+', '').replace(' ', '')
    wa_text = f"مرحباً متجر وَقّار، قمت بالطلب من الموقع برقم: {order['order_number']}%0Aالاسم: {order['customer_name']}%0Aالمبلغ الإجمالي: {order['total_amount']:.2f} د.أ%0Aأرجو تأكيد الطلب والتوصيل."
    whatsapp_url = f"https://wa.me/{whatsapp_num}?text={wa_text}"

    return render_template(
        'order_confirmation.html',
        order=order,
        items=items,
        whatsapp_url=whatsapp_url
    )

@store_bp.route('/track-order', methods=['GET', 'POST'])
def track_order():
    """Live Order Tracking Timeline."""
    order = None
    items = []
    error = None

    if request.method == 'POST':
        order_num = request.form.get('order_number', '').strip()
        phone = request.form.get('phone', '').strip()

        clean_phone = phone.replace(' ', '').replace('-', '').replace('+962', '0')
        if not order_num or not phone:
            error = 'يرجى إدخال رقم الطلب ورقم الهاتف.'
        else:
            conn = get_db()
            # Accept with or without '#'
            search_num = order_num if order_num.startswith('#') else f"#{order_num}"
            order = conn.execute('''
                SELECT * FROM orders
                WHERE (order_number = ? OR order_number = ?) AND (customer_phone LIKE ? OR customer_phone = ?)
            ''', (search_num, order_num, f"%{clean_phone[-9:]}%", clean_phone)).fetchone()

            if order:
                items = conn.execute("SELECT * FROM order_items WHERE order_id = ?", (order['id'],)).fetchall()
            else:
                error = 'لم يتم العثور على أي طلب يطابق البيانات المدخلة. يرجى التأكد من رقم الطلب ورقم الهاتف.'
            conn.close()

    return render_template('track_order.html', order=order, items=items, error=error)

@store_bp.route('/wishlist')
def wishlist():
    """Customer Wishlist."""
    wishlist_ids = session.get('wishlist', [])
    products = []

    if wishlist_ids:
        conn = get_db()
        placeholders = ','.join('?' for _ in wishlist_ids)
        products = conn.execute(f'''
            SELECT p.*, c.name as category_name,
                   (SELECT image_url FROM product_images WHERE product_id = p.id ORDER BY is_primary DESC, sort_order ASC LIMIT 1) as primary_image,
                   (SELECT GROUP_CONCAT(DISTINCT color_hex) FROM product_variants WHERE product_id = p.id) as colors_hex,
                   (SELECT GROUP_CONCAT(DISTINCT size_name) FROM product_variants WHERE product_id = p.id) as sizes_list,
                   (SELECT SUM(stock_quantity) FROM product_variants WHERE product_id = p.id) as total_stock
            FROM products p
            LEFT JOIN categories c ON p.category_id = c.id
            WHERE p.id IN ({placeholders}) AND p.is_published = 1
        ''', wishlist_ids).fetchall()
        conn.close()

    return render_template('wishlist.html', products=products)

# =========================================================================
# Informational & Policy Pages
# =========================================================================

@store_bp.route('/about')
def about():
    return render_template('pages/about.html')

@store_bp.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone')
        message = request.form.get('message')
        flash('شكراً لتواصلك مع متجر وَقّار، سيتم الرد عليك في أقرب وقت.', 'success')
        return redirect(url_for('store.contact'))
    return render_template('pages/contact.html')

@store_bp.route('/privacy')
def privacy():
    return render_template('pages/privacy.html')

@store_bp.route('/terms')
def terms():
    return render_template('pages/terms.html')

@store_bp.route('/returns')
def returns():
    return render_template('pages/returns.html')

# =========================================================================
# AJAX & API Endpoints
# =========================================================================

@store_bp.route('/api/cart/add', methods=['POST'])
def api_add_to_cart():
    """AJAX Add to Cart with Variant and Stock Validation."""
    data = request.get_json() or {}
    product_id = data.get('product_id')
    color = data.get('color', '').strip()
    size = data.get('size', '').strip()
    quantity = int(data.get('quantity', 1))

    if not product_id or not color or not size:
        return jsonify({'success': False, 'message': 'يرجى اختيار اللون والمقاس أولاً.'}), 400

    conn = get_db()
    # Check variant stock
    variant = conn.execute('''
        SELECT stock_quantity FROM product_variants
        WHERE product_id = ? AND color_name = ? AND size_name = ?
    ''', (product_id, color, size)).fetchone()

    if not variant:
        conn.close()
        return jsonify({'success': False, 'message': 'المقاس أو اللون المحدد غير متوفر.'}), 400

    current_stock = variant['stock_quantity']
    cart = session.get('cart', {})
    cart_key = f"{product_id}_{color}_{size}"

    existing_qty = cart.get(cart_key, {}).get('quantity', 0)
    new_qty = existing_qty + quantity

    if new_qty > current_stock:
        conn.close()
        return jsonify({
            'success': False,
            'message': f'الكمية المطلوبة غير متوفرة بالمخزون. المتاح حالياً: {current_stock}'
        }), 400

    cart[cart_key] = {
        'product_id': product_id,
        'color': color,
        'size': size,
        'quantity': new_qty
    }
    session['cart'] = cart
    session.modified = True

    total_cart_count = sum(item['quantity'] for item in cart.values())
    conn.close()

    return jsonify({
        'success': True,
        'message': 'تمت إضافة المنتج إلى سلة الشراء بنجاح.',
        'cart_count': total_cart_count
    })

@store_bp.route('/api/cart/update', methods=['POST'])
def api_update_cart():
    """AJAX Update Cart Item Quantity."""
    data = request.get_json() or {}
    cart_key = data.get('key')
    quantity = int(data.get('quantity', 1))

    cart = session.get('cart', {})
    if cart_key not in cart:
        return jsonify({'success': False, 'message': 'العنصر غير موجود في السلة.'}), 404

    item = cart[cart_key]

    conn = get_db()
    variant = conn.execute('''
        SELECT stock_quantity FROM product_variants
        WHERE product_id = ? AND color_name = ? AND size_name = ?
    ''', (item['product_id'], item['color'], item['size'])).fetchone()
    conn.close()

    if variant and quantity > variant['stock_quantity']:
        return jsonify({
            'success': False,
            'message': f"الكمية المتوفرة بالمخزون هي {variant['stock_quantity']} فقط."
        }), 400

    if quantity <= 0:
        cart.pop(cart_key, None)
    else:
        cart[cart_key]['quantity'] = quantity

    session['cart'] = cart
    session.modified = True

    total_cart_count = sum(i['quantity'] for i in cart.values())
    return jsonify({
        'success': True,
        'message': 'تم تحديث السلة بنجاح.',
        'cart_count': total_cart_count
    })

@store_bp.route('/api/cart/remove', methods=['POST'])
def api_remove_from_cart():
    """AJAX Remove Item from Cart."""
    data = request.get_json() or {}
    cart_key = data.get('key')

    cart = session.get('cart', {})
    if cart_key in cart:
        cart.pop(cart_key, None)
        session['cart'] = cart
        session.modified = True

    total_cart_count = sum(i['quantity'] for i in cart.values())
    return jsonify({
        'success': True,
        'message': 'تم حذف المنتج من السلة.',
        'cart_count': total_cart_count
    })

@store_bp.route('/api/coupon/apply', methods=['POST'])
def api_apply_coupon():
    """Apply Coupon code."""
    data = request.get_json() or {}
    code = data.get('code', '').strip().upper()

    if not code:
        return jsonify({'success': False, 'message': 'يرجى إدخال رمز الكوبون.'}), 400

    conn = get_db()
    coupon = conn.execute("SELECT * FROM coupons WHERE code = ? AND is_active = 1", (code,)).fetchone()
    conn.close()

    if not coupon:
        return jsonify({'success': False, 'message': 'كود الكوبون غير صالح أو منتهي الصلاحية.'}), 400

    # Store in session
    session['applied_coupon'] = {
        'code': coupon['code'],
        'discount_type': coupon['discount_type'],
        'discount_value': coupon['discount_value'],
        'min_order_amount': coupon['min_order_amount']
    }
    session.modified = True

    return jsonify({
        'success': True,
        'message': f"تم تطبيق الكوبون {coupon['code']} بنجاح!",
        'coupon': session['applied_coupon']
    })

@store_bp.route('/api/coupon/remove', methods=['POST'])
def api_remove_coupon():
    """Remove Coupon code."""
    session.pop('applied_coupon', None)
    session.modified = True
    return jsonify({'success': True, 'message': 'تمت إزالة الكوبون.'})

@store_bp.route('/api/wishlist/toggle', methods=['POST'])
def api_toggle_wishlist():
    """Toggle product in wishlist."""
    data = request.get_json() or {}
    product_id = data.get('product_id')

    if not product_id:
        return jsonify({'success': False, 'message': 'معرف المنتج مطلوب.'}), 400

    wishlist = session.get('wishlist', [])
    if not isinstance(wishlist, list):
        wishlist = []

    if product_id in wishlist:
        wishlist.remove(product_id)
        action = 'removed'
        msg = 'تمت إزالة المنتج من المفضلة.'
    else:
        wishlist.append(product_id)
        action = 'added'
        msg = 'تمت إضافة المنتج إلى المفضلة ❤️'

    session['wishlist'] = wishlist
    session.modified = True

    return jsonify({
        'success': True,
        'action': action,
        'message': msg,
        'wishlist_count': len(wishlist)
    })

@store_bp.route('/api/search/suggestions')
def api_search_suggestions():
    """Live search suggestions endpoint."""
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify({'results': []})

    conn = get_db()
    results = conn.execute('''
        SELECT p.id, p.name, p.slug, p.base_price, p.discount_price, c.name as category_name,
               (SELECT image_url FROM product_images WHERE product_id = p.id ORDER BY is_primary DESC, sort_order ASC LIMIT 1) as image
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        WHERE p.is_published = 1 AND (p.name LIKE ? OR c.name LIKE ?)
        LIMIT 6
    ''', (f"%{q}%", f"%{q}%")).fetchall()
    conn.close()

    data = [
        {
            'id': r['id'],
            'name': r['name'],
            'slug': r['slug'],
            'price': r['discount_price'] or r['base_price'],
            'category': r['category_name'],
            'image': r['image'] or '/static/images/placeholder.svg'
        } for r in results
    ]
    return jsonify({'results': data})

@store_bp.route('/api/reviews/submit', methods=['POST'])
def api_submit_review():
    """Submit Product Review."""
    data = request.get_json() or {}
    product_id = data.get('product_id')
    name = data.get('name', '').strip()
    rating = int(data.get('rating', 5))
    comment = data.get('comment', '').strip()

    if not product_id or not name or not comment:
        return jsonify({'success': False, 'message': 'يرجى كتابة الاسم والتقييم والتعليق.'}), 400

    conn = get_db()
    conn.execute('''
        INSERT INTO product_reviews (product_id, customer_name, rating, comment, is_approved)
        VALUES (?, ?, ?, ?, 0)
    ''', (product_id, name, rating, comment))
    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'message': 'شكراً لك! تم استلام تقييمك بنجاح وسيتم نشره بعد مراجعته من الإدارة.'
    })

