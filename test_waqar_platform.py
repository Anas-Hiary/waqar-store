import unittest
import json
from app import create_app
from database import init_db, get_db, get_setting, generate_order_number
from seed_data import seed_all

class WaqarStoreTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()
        seed_all()

    def test_database_seeded_properly(self):
        """Test database tables and initial seed data."""
        conn = get_db()
        # Verify Admins
        admin = conn.execute("SELECT * FROM admins WHERE username = 'admin'").fetchone()
        self.assertIsNotNone(admin)
        
        # Verify Categories (Men's clothing only)
        cats = conn.execute("SELECT * FROM categories").fetchall()
        self.assertGreaterEqual(len(cats), 8)

        # Verify Products
        prods = conn.execute("SELECT * FROM products").fetchall()
        self.assertGreaterEqual(len(prods), 5)

        # Verify Variants
        variants = conn.execute("SELECT * FROM product_variants").fetchall()
        self.assertGreaterEqual(len(variants), 10)

        # Verify Delivery Zones
        zones = conn.execute("SELECT * FROM delivery_zones").fetchall()
        self.assertGreaterEqual(len(zones), 5)

        conn.close()

    def test_public_pages(self):
        """Test public customer-facing routes."""
        # 1. Homepage
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        self.assertIn('وَقّار'.encode('utf-8'), res.data)
        self.assertIn('أناقتك تبدأ من وَقّار'.encode('utf-8'), res.data)

        # 2. Shop page
        res = self.client.get('/shop')
        self.assertEqual(res.status_code, 200)

        # 3. Product detail page
        res = self.client.get('/product/luxury-classic-mens-shirt')
        self.assertEqual(res.status_code, 200)
        self.assertIn('قميص رجالي كلاسيك فاخر'.encode('utf-8'), res.data)
        self.assertIn('دليل المقاسات'.encode('utf-8'), res.data)

        # 4. Cart page
        res = self.client.get('/cart')
        self.assertEqual(res.status_code, 200)

        # 5. Track Order page
        res = self.client.get('/track-order')
        self.assertEqual(res.status_code, 200)

        # 6. Policy Pages
        for page in ['/about', '/contact', '/privacy', '/terms', '/returns']:
            res = self.client.get(page)
            self.assertEqual(res.status_code, 200)

    def test_ajax_cart_and_variants(self):
        """Test adding items to cart with variant validation."""
        conn = get_db()
        prod = conn.execute("SELECT id FROM products WHERE slug = 'luxury-classic-mens-shirt'").fetchone()
        conn.close()

        # Add valid item to cart
        res = self.client.post('/api/cart/add', json={
            'product_id': prod['id'],
            'color': 'أبيض',
            'size': 'M',
            'quantity': 2
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['cart_count'], 2)

        # Add out-of-stock item (Black XL has 0 stock in seed data)
        res = self.client.post('/api/cart/add', json={
            'product_id': prod['id'],
            'color': 'أسود',
            'size': 'XL',
            'quantity': 1
        })
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data['success'])

    def test_coupon_api(self):
        """Test coupon application."""
        res = self.client.post('/api/coupon/apply', json={'code': 'WAQAR10'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['coupon']['code'], 'WAQAR10')

    def test_complete_checkout_and_order_flow(self):
        """Test full checkout flow with Cash on Delivery and stock deduction."""
        conn = get_db()
        prod = conn.execute("SELECT id FROM products WHERE slug = 'luxury-classic-mens-shirt'").fetchone()
        zone = conn.execute("SELECT id FROM delivery_zones WHERE governorate_name = 'السلط'").fetchone()
        
        # Check initial stock
        initial_variant = conn.execute(
            "SELECT stock_quantity FROM product_variants WHERE product_id = ? AND color_name = 'أبيض' AND size_name = 'M'",
            (prod['id'],)
        ).fetchone()
        initial_stock = initial_variant['stock_quantity']
        conn.close()

        # 1. Add to cart
        self.client.post('/api/cart/add', json={
            'product_id': prod['id'],
            'color': 'أبيض',
            'size': 'M',
            'quantity': 2
        })

        # 2. Submit Checkout form
        res = self.client.post('/checkout', data={
            'full_name': 'محمد العبادي',
            'phone': '0796667505',
            'governorate_id': zone['id'],
            'city': 'السلط',
            'address': 'الشارع الرئيسي بجانب مسجد السلط الكبير',
            'notes': 'يرجى الاتصال قبل الوصول بنصف ساعة'
        }, follow_redirects=True)

        self.assertEqual(res.status_code, 200)
        self.assertIn('تم استلام طلبك بنجاح'.encode('utf-8'), res.data)
        self.assertIn('#WAQ-'.encode('utf-8'), res.data)

        # 3. Verify stock deduction in database
        conn = get_db()
        updated_variant = conn.execute(
            "SELECT stock_quantity FROM product_variants WHERE product_id = ? AND color_name = 'أبيض' AND size_name = 'M'",
            (prod['id'],)
        ).fetchone()
        self.assertEqual(updated_variant['stock_quantity'], initial_stock - 2)

        # 4. Verify order in database
        order = conn.execute("SELECT * FROM orders WHERE customer_phone = '0796667505' ORDER BY id DESC LIMIT 1").fetchone()
        self.assertIsNotNone(order)
        self.assertEqual(order['customer_name'], 'محمد العبادي')
        self.assertEqual(order['customer_governorate'], 'السلط')
        conn.close()

        # 5. Test Track Order
        track_res = self.client.post('/track-order', data={
            'order_number': order['order_number'],
            'phone': '0796667505'
        })
        self.assertEqual(track_res.status_code, 200)
        self.assertIn('طلب جديد'.encode('utf-8'), track_res.data)

    def test_admin_auth_and_dashboard(self):
        """Test Admin login, authentication protection, and dashboard metrics."""
        # 1. Access protected admin without login
        res = self.client.get('/admin/dashboard', follow_redirects=True)
        self.assertIn('تسجيل دخول الإدارة'.encode('utf-8'), res.data)

        # 2. Login with valid admin credentials
        login_res = self.client.post('/admin/login', data={
            'username': 'admin',
            'password': 'admin123'
        }, follow_redirects=True)
        self.assertEqual(login_res.status_code, 200)
        self.assertIn('لوحة وَقّار'.encode('utf-8'), login_res.data)
        self.assertIn('إجمالي المبيعات'.encode('utf-8'), login_res.data)

        # 3. Access admin products
        prod_res = self.client.get('/admin/products')
        self.assertEqual(prod_res.status_code, 200)

        # 4. Access admin inventory
        inv_res = self.client.get('/admin/inventory')
        self.assertEqual(inv_res.status_code, 200)

        # 5. Access admin orders
        ord_res = self.client.get('/admin/orders')
        self.assertEqual(ord_res.status_code, 200)

        # 6. Access admin delivery zones
        del_res = self.client.get('/admin/delivery-zones')
        self.assertEqual(del_res.status_code, 200)

        # 7. Access admin coupons
        coup_res = self.client.get('/admin/coupons')
        self.assertEqual(coup_res.status_code, 200)

        # 8. Access admin homepage editor
        home_res = self.client.get('/admin/homepage')
        self.assertEqual(home_res.status_code, 200)

        # 9. Access admin settings
        set_res = self.client.get('/admin/settings')
        self.assertEqual(set_res.status_code, 200)

if __name__ == '__main__':
    unittest.main()

