import os
import json
from werkzeug.security import generate_password_hash
from database import init_db, get_db, set_setting, is_postgres, reset_postgres_sequences

def seed_all():
    init_db()
    conn = get_db()
    cursor = conn.cursor()

    # 1. Seed Admin User
    admin_exists = cursor.execute("SELECT id FROM admins WHERE username = 'admin'").fetchone()
    if not admin_exists:
        cursor.execute('''
        INSERT INTO admins (username, email, password_hash, full_name)
        VALUES (?, ?, ?, ?)
        ''', (
            'admin',
            'admin@waqar-fashion.com',
            generate_password_hash('admin123'),
            'مدير متجر وَقّار'
        ))

    # 2. Seed Store Settings
    settings = {
        'store_name': 'وَقّار',
        'store_business': 'أزياء وملابس رجالية',
        'tagline': 'أناقتك تبدأ من وَقّار',
        'city': 'السلط',
        'country': 'الأردن',
        'phone': '0796667505',
        'whatsapp': '+962796667505',
        'instagram': '@waqar_fashion199',
        'instagram_url': 'https://www.instagram.com/waqar_fashion199',
        'hero_title': 'أناقتك تبدأ من وَقّار',
        'hero_subtitle': 'اكتشف أحدث تشكيلات الأزياء الرجالية الفاخرة - تصاميم عصرية وجودة لا تضاهى',
        'hero_btn1_text': 'تسوق الآن',
        'hero_btn1_url': '/shop',
        'hero_btn2_text': 'وصل حديثاً',
        'hero_btn2_url': '/shop?filter=new',
        'hero_image': 'https://images.unsplash.com/photo-1617137984095-74e4e5e3613f?auto=format&fit=crop&w=1600&q=80',
        'store_address': 'السلط، الأردن - بالقرب من مركز المدينة',
        'google_maps_embed': 'https://www.google.com/maps/embed?pb=!1m18!1m12!1m3!1d54109.82027202356!2d35.70889279599609!3d32.03917415494247!2m3!1f0!2f0!3f0!3m2!1i1024!2i768!4f13.1!3m3!1m2!1s0x151ca79e49635f79%3A0xbce5c1507d4b4a39!2sAs-Salt!5e0!3m2!1sen!2sjo!4v1700000000000!5m2!1sen!2sjo',
        'working_hours': 'يومياً من 10:00 صباحاً حتى 11:00 مساءً (الجمعة من 2:00 ظهراً)',
        'announcement_bar': '✨ تشكيلة رجالية حصرية جديدة | توصيل سريع لكافة أنحاء الأردن | الدفع عند الاستلام ✨',
        'free_delivery_threshold': '50',
        'why_waqar_1_title': 'تشكيلة رجالية عصرية',
        'why_waqar_1_desc': 'أحدث صيحات الموضة والقصات الرجالية الكلاسيكية والحديثة.',
        'why_waqar_2_title': 'جودة مختارة بعناية',
        'why_waqar_2_desc': 'أقمشة فاخرة وخياطة متقنة تدوم طويلاً وتمنحك راحة تامة.',
        'why_waqar_3_title': 'طلب أونلاين بسهولة',
        'why_waqar_3_desc': 'تجربة تسوق سهلة وسريعة مع خيار الدفع عند الاستلام.',
        'why_waqar_4_title': 'توصيل سريع داخل الأردن',
        'why_waqar_4_desc': 'شحن وتوصيل فوري في السلط وعمان وجميع محافظات المملكة.',
        'exchange_policy': 'يسر متجر وَقّار توفير سياسة استبدال واسترجاع ميسرة خلال 3 أيام من تاريخ الاستلام. يشترط أن يكون المنتج بحالته الأصلية غير مستخدم ومرفقاً بكافة البطاقات والتغليف الأصلي.',
        'privacy_policy': 'نحن في متجر وَقّار نلتزم بالحفاظ على سرية وخصوصية بياناتكم الشخصية. يتم استخدام معلومات الاتصال والعنوان حصرياً لمعالجة وتوصيل طلباتكم والتواصل معكم بشأنها.',
        'terms_conditions': 'تخضع جميع الطلبات على الموقع لسياسة التأكيد عبر الهاتف أو الواتساب قبل الشحن. الأسعار المعروضة بالدينار الأردني وتشمل الرسوم الموضحة في ملخص الطلب.'
    }

    for k, v in settings.items():
        cursor.execute("INSERT OR IGNORE INTO store_settings (key, value) VALUES (?, ?)", (k, str(v)))

    # 3. Seed Delivery Zones (Jordan Governorates)
    zones = [
        ('السلط', 1.50, 'خلال 24 ساعة', 1),
        ('عمّان', 2.00, '24 - 48 ساعة', 1),
        ('الزرقاء', 2.50, '24 - 48 ساعة', 1),
        ('إربد', 3.00, '2 - 3 أيام', 1),
        ('مادبا', 2.50, '24 - 48 ساعة', 1),
        ('جرش وعجلون', 3.00, '2 - 3 أيام', 1),
        ('الكرك والطفيلة ومعان والعقبة', 3.50, '2 - 3 أيام', 1),
        ('باقي المحافظات والمناطق', 3.50, '2 - 3 أيام', 1),
    ]

    for name, fee, est, active in zones:
        cursor.execute('''
        INSERT OR IGNORE INTO delivery_zones (governorate_name, fee, estimated_time, is_active)
        VALUES (?, ?, ?, ?)
        ''', (name, fee, est, active))

    # 4. Seed Categories (Men's clothing categories only - NO accessories)
    categories = [
        ('قمصان', 'shirts', 'قمصان رجالية كلاسيكية وكاجوال بأرقى الأقمشة والقصات', 'https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?auto=format&fit=crop&w=600&q=80', 1),
        ('تيشيرتات', 't-shirts', 'تيشيرتات قطنية وبولو بتصاميم عصرية مريحة', 'https://images.unsplash.com/photo-1521572267360-ee0c2909d518?auto=format&fit=crop&w=600&q=80', 2),
        ('بناطيل', 'trousers', 'بناطيل قماش وشينو وكلاسيك لمختلف المناسبات', 'https://images.unsplash.com/photo-1624378439575-d8705ad7ae80?auto=format&fit=crop&w=600&q=80', 3),
        ('جينز', 'jeans', 'جينزات رجالية بقصات عصرية ومتانة عالية', 'https://images.unsplash.com/photo-1542272604-780c96856592?auto=format&fit=crop&w=600&q=80', 4),
        ('جاكيتات', 'jackets', 'جاكيتات شتوية وسترات بومبر وبليزر فاخرة', 'https://images.unsplash.com/photo-1551028719-00167b16eac5?auto=format&fit=crop&w=600&q=80', 5),
        ('بدلات', 'suits', 'بدلات رجالية رسمية لإطلالة راقية في مناسباتك المهمة', 'https://images.unsplash.com/photo-1594938298603-c8148c4dae35?auto=format&fit=crop&w=600&q=80', 6),
        ('أطقم', 'sets', 'أطقم كاجوال ورياضية متناسقة بأعلى مستويات الأناقة', 'https://images.unsplash.com/photo-1507679799987-c73779587ccf?auto=format&fit=crop&w=600&q=80', 7),
        ('ملابس رياضية', 'sportswear', 'ملابس رياضية مريحة ومرنة للتدريب والإطلالات اليومية', 'https://images.unsplash.com/photo-1517838277536-f5f99be501cd?auto=format&fit=crop&w=600&q=80', 8),
        ('ملابس شتوية', 'winter', 'سترات صوفية ومعاطف وهوديات شتوية دافئة', 'https://images.unsplash.com/photo-1578632767115-351597cf2477?auto=format&fit=crop&w=600&q=80', 9),
        ('ملابس صيفية', 'summer', 'ملابس كتان وتشكيلات خفيفة ومريحة لفصل الصيف', 'https://images.unsplash.com/photo-1503342217505-b0a15ec3261c?auto=format&fit=crop&w=600&q=80', 10),
    ]

    cat_map = {}
    for name, slug, desc, img, order in categories:
        row = cursor.execute("SELECT id FROM categories WHERE slug = ?", (slug,)).fetchone()
        if not row:
            cursor.execute('''
            INSERT INTO categories (name, slug, description, image_url, display_order, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
            ''', (name, slug, desc, img, order))
            cat_map[slug] = cursor.lastrowid
        else:
            cat_map[slug] = row['id']

    # 5. Seed Coupons
    coupons = [
        ('WAQAR10', 'percent', 10.0, 15.0, 100, 1),
        ('SALT2026', 'fixed', 2.0, 20.0, 100, 1),
        ('WELCOME', 'percent', 15.0, 30.0, 50, 1)
    ]
    for code, dtype, val, min_amt, max_u, active in coupons:
        cursor.execute('''
        INSERT OR IGNORE INTO coupons (code, discount_type, discount_value, min_order_amount, max_uses, is_active)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (code, dtype, val, min_amt, max_u, active))

    # 6. Seed Realistic Demo Men's Clothing Products
    # Each product with colors, sizes, stock quantity, material, fit, and photos
    demo_products = [
        {
            'name': 'قميص رجالي كلاسيك فاخر',
            'slug': 'luxury-classic-mens-shirt',
            'category': 'shirts',
            'base_price': 24.00,
            'discount_price': 18.50,
            'sku': 'WQ-SH-001',
            'material': 'قطن مصري 100% عالي الجودة',
            'fit': 'سليم فيت (Slim Fit)',
            'season': 'جميع المواسم',
            'care_instructions': 'غسيل يدوي أو آلي بدرجة حرارة 30 مئوية، كي بدرجة حرارة متوسطة',
            'is_featured': 1,
            'is_new': 1,
            'is_bestseller': 1,
            'is_offer': 1,
            'description': 'قميص كلاسيكي أنيق مصمم خصيصاً للرجل العصري. مصنوع من أجود خيوط القطن المصري التي تمنحك ملمساً فائق النعومة وتهوية مثالية طوال اليوم. مناسب للاجتماعات الرسمية والمناسبات الخاصة.',
            'images': [
                'https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?auto=format&fit=crop&w=800&q=80',
                'https://images.unsplash.com/photo-1596755094514-f87e34085b2c?auto=format&fit=crop&w=800&q=80',
                'https://images.unsplash.com/photo-1603252109303-2751441dd157?auto=format&fit=crop&w=800&q=80'
            ],
            'variants': [
                ('أبيض', '#ffffff', 'M', 6),
                ('أبيض', '#ffffff', 'L', 8),
                ('أبيض', '#ffffff', 'XL', 4),
                ('أبيض', '#ffffff', 'XXL', 2),
                ('أسود', '#111111', 'M', 5),
                ('أسود', '#111111', 'L', 7),
                ('أسود', '#111111', 'XL', 0), # Out of stock test
                ('كحلي', '#1a2b49', 'M', 4),
                ('كحلي', '#1a2b49', 'L', 6),
                ('كحلي', '#1a2b49', 'XL', 3)
            ]
        },
        {
            'name': 'تيشيرت بولو قطن بريميوم',
            'slug': 'premium-cotton-polo-shirt',
            'category': 't-shirts',
            'base_price': 16.00,
            'discount_price': 12.99,
            'sku': 'WQ-TS-002',
            'material': 'قطن بيكيه 95%، إيلاستين 5%',
            'fit': 'ريجولار فيت (Regular Fit)',
            'season': 'صيفي / ربيعي',
            'care_instructions': 'غسيل آلي بماء بارد مع ألوان مشابهة، تجنب المبيضات',
            'is_featured': 1,
            'is_new': 1,
            'is_bestseller': 1,
            'is_offer': 1,
            'description': 'تيشيرت بولو رجالي فاخر بياقة كلاسيكية محبوكة وأزرار أنيقة. يمنحك التوازن المثالي بين الطابع الرياضي والأناقة غير الرسمية ليناسب أيام العمل والطلعات اليومية.',
            'images': [
                'https://images.unsplash.com/photo-1581655353564-df123a1eb820?auto=format&fit=crop&w=800&q=80',
                'https://images.unsplash.com/photo-1521572267360-ee0c2909d518?auto=format&fit=crop&w=800&q=80'
            ],
            'variants': [
                ('كحلي', '#1a2b49', 'S', 3),
                ('كحلي', '#1a2b49', 'M', 8),
                ('كحلي', '#1a2b49', 'L', 10),
                ('كحلي', '#1a2b49', 'XL', 5),
                ('رمادي غامق', '#374151', 'M', 6),
                ('رمادي غامق', '#374151', 'L', 8),
                ('رمادي غامق', '#374151', 'XL', 4),
                ('زيتوني', '#4b5320', 'M', 4),
                ('زيتوني', '#4b5320', 'L', 5)
            ]
        },
        {
            'name': 'بنطلون جينز رجالي قصة مستقيمة',
            'slug': 'mens-straight-fit-jeans',
            'category': 'jeans',
            'base_price': 28.00,
            'discount_price': 22.00,
            'sku': 'WQ-JN-003',
            'material': 'دنيم قطني 98%، ليكرا 2%',
            'fit': 'ستريت فيت (Straight Fit)',
            'season': 'جميع المواسم',
            'care_instructions': 'يغسل مقلوباً بماء بارد للحفاظ على اللون الأصلي',
            'is_featured': 1,
            'is_new': 0,
            'is_bestseller': 1,
            'is_offer': 1,
            'description': 'بنطلون جينز رجالي فائق الراحة مصنوع من خامة الدنيم المتينة مع مرونة خفيفة تسمح بحرية الحركة طوال اليوم. غسيل داكن متميز يضفي مظهراً جذاباً.',
            'images': [
                'https://images.unsplash.com/photo-1542272604-780c96856592?auto=format&fit=crop&w=800&q=80',
                'https://images.unsplash.com/photo-1541099649105-f69ad21f3246?auto=format&fit=crop&w=800&q=80'
            ],
            'variants': [
                ('أزرق داكن', '#1e293b', '30', 4),
                ('أزرق داكن', '#1e293b', '32', 7),
                ('أزرق داكن', '#1e293b', '34', 8),
                ('أزرق داكن', '#1e293b', '36', 5),
                ('أزرق فاتح', '#64748b', '32', 4),
                ('أزرق فاتح', '#64748b', '34', 6),
                ('أسود كربوني', '#18181b', '32', 5),
                ('أسود كربوني', '#18181b', '34', 5)
            ]
        },
        {
            'name': 'جاكيت بليزر كاجوال عصري',
            'slug': 'mens-modern-casual-blazer',
            'category': 'jackets',
            'base_price': 48.00,
            'discount_price': 39.00,
            'sku': 'WQ-JK-004',
            'material': 'مزيج صوف وكتان إيطالي عالي الجودة',
            'fit': 'مودرن فيت (Modern Fit)',
            'season': 'شتوي / خريفي',
            'care_instructions': 'تنظيف جاف فقط (Dry Clean)',
            'is_featured': 1,
            'is_new': 1,
            'is_bestseller': 0,
            'is_offer': 1,
            'description': 'جاكيت بليزر رجالي استثنائي يجمع بين الفخامة والعملية. مبطن بعناية مع تفاصيل جيوب متقنة وأزرار فاخرة لتتألق في مختلف الإطلالات الرسمية وشبه الرسمية.',
            'images': [
                'https://images.unsplash.com/photo-1507679799987-c73779587ccf?auto=format&fit=crop&w=800&q=80',
                'https://images.unsplash.com/photo-1594938298603-c8148c4dae35?auto=format&fit=crop&w=800&q=80'
            ],
            'variants': [
                ('كحلي ملكي', '#0f172a', '48', 3),
                ('كحلي ملكي', '#0f172a', '50', 5),
                ('كحلي ملكي', '#0f172a', '52', 4),
                ('كحلي ملكي', '#0f172a', '54', 2),
                ('رمادي فحمي', '#334155', '50', 4),
                ('رمادي فحمي', '#334155', '52', 3)
            ]
        },
        {
            'name': 'بنطلون شينو قماش كلاسيك',
            'slug': 'mens-classic-chino-trousers',
            'category': 'trousers',
            'base_price': 22.00,
            'discount_price': None,
            'sku': 'WQ-TR-005',
            'material': 'قطن تويل 97%، إيلاستين 3%',
            'fit': 'سليم فيت (Slim Fit)',
            'season': 'جميع المواسم',
            'care_instructions': 'غسيل آلي عادي بدرجة حرارة معتدلة',
            'is_featured': 0,
            'is_new': 1,
            'is_bestseller': 1,
            'is_offer': 0,
            'description': 'بنطلون شينو أنيق بقصة عصرية وخياطة متينة. مثالي للارتداء اليومي مع القمصان أو التيشيرتات لإطلالة ذكية مريحة.',
            'images': [
                'https://images.unsplash.com/photo-1624378439575-d8705ad7ae80?auto=format&fit=crop&w=800&q=80',
                'https://images.unsplash.com/photo-1479064555552-3ef4979f8908?auto=format&fit=crop&w=800&q=80'
            ],
            'variants': [
                ('بيج كاكي', '#d4b996', '30', 3),
                ('بيج كاكي', '#d4b996', '32', 6),
                ('بيج كاكي', '#d4b996', '34', 6),
                ('بيج كاكي', '#d4b996', '36', 4),
                ('كحلي', '#1e293b', '32', 5),
                ('كحلي', '#1e293b', '34', 5),
                ('زيتوني', '#3f4a3c', '32', 3),
                ('زيتوني', '#3f4a3c', '34', 4)
            ]
        },
        {
            'name': 'طقم رياضي رجالي قطني متكامل',
            'slug': 'mens-cotton-tracksuit-set',
            'category': 'sportswear',
            'base_price': 35.00,
            'discount_price': 29.50,
            'sku': 'WQ-SP-006',
            'material': 'قطن فليس معالج 80%، بوليستر 20%',
            'fit': 'كومفورت فيت (Comfort Fit)',
            'season': 'شتوي / خريفي',
            'care_instructions': 'غسيل آلي بماء فاتر وتجفيف بدرجة منخفضة',
            'is_featured': 1,
            'is_new': 1,
            'is_bestseller': 0,
            'is_offer': 1,
            'description': 'طقم رياضي فخم يتكون من سترة بسحاب وبنطلون رياضي مريح بجيوب جانبية. مصمم لمنحك الراحة القصوى أثناء التمارين أو الأنشطة اليومية.',
            'images': [
                'https://images.unsplash.com/photo-1517838277536-f5f99be501cd?auto=format&fit=crop&w=800&q=80',
                'https://images.unsplash.com/photo-1556906781-9a412961c28c?auto=format&fit=crop&w=800&q=80'
            ],
            'variants': [
                ('أسود بالكامل', '#09090b', 'M', 5),
                ('أسود بالكامل', '#09090b', 'L', 7),
                ('أسود بالكامل', '#09090b', 'XL', 6),
                ('أسود بالكامل', '#09090b', 'XXL', 3),
                ('رمادي ميلانج', '#71717a', 'M', 4),
                ('رمادي ميلانج', '#71717a', 'L', 6),
                ('رمادي ميلانج', '#71717a', 'XL', 5)
            ]
        },
        {
            'name': 'بدلة رجالية رسمية إيطالية كاملة',
            'slug': 'mens-italian-formal-suit',
            'category': 'suits',
            'base_price': 85.00,
            'discount_price': 69.00,
            'sku': 'WQ-ST-007',
            'material': 'صوف سوبر 120 إيطالي نقي',
            'fit': 'تايلورد فيت (Tailored Fit)',
            'season': 'جميع المواسم',
            'care_instructions': 'تنظيف جاف احترافي فقط، حفظ في غطاء واقي من الغبار',
            'is_featured': 1,
            'is_new': 0,
            'is_bestseller': 1,
            'is_offer': 1,
            'description': 'بدلة رجالية ملكية قطعتين (جاكيت + بنطلون) بتفصيل دقيق وقصة مريحة تمنحك إطلالة مهيبة في الأفراح والمناسبات الراقية ورجال الأعمال.',
            'images': [
                'https://images.unsplash.com/photo-1594938298603-c8148c4dae35?auto=format&fit=crop&w=800&q=80',
                'https://images.unsplash.com/photo-1507679799987-c73779587ccf?auto=format&fit=crop&w=800&q=80'
            ],
            'variants': [
                ('كحلي داكن', '#020617', '48', 2),
                ('كحلي داكن', '#020617', '50', 4),
                ('كحلي داكن', '#020617', '52', 4),
                ('كحلي داكن', '#020617', '54', 2),
                ('أسود كلاسيك', '#000000', '48', 3),
                ('أسود كلاسيك', '#000000', '50', 5),
                ('أسود كلاسيك', '#000000', '52', 3)
            ]
        },
        {
            'name': 'جاكيت بامب شتوي عازل للماء',
            'slug': 'mens-winter-puffer-jacket',
            'category': 'winter',
            'base_price': 42.00,
            'discount_price': 34.00,
            'sku': 'WQ-JK-008',
            'material': 'بوليستر مقاوم للماء والرياح مع حشوة فايبر حرارية',
            'fit': 'ريجولار فيت (Regular Fit)',
            'season': 'شتوي',
            'care_instructions': 'غسيل آلي خفيف بماء بارد دون استخدام مجفف حراري',
            'is_featured': 1,
            'is_new': 1,
            'is_bestseller': 1,
            'is_offer': 1,
            'description': 'جاكيت شتوي مبطن ومقاوم للأمطار والبرد القارس. يحتوي على غطاء رأس قابل للفصل وجيوب دافئة مبطنة بالفرو الناعم.',
            'images': [
                'https://images.unsplash.com/photo-1551028719-00167b16eac5?auto=format&fit=crop&w=800&q=80',
                'https://images.unsplash.com/photo-1578632767115-351597cf2477?auto=format&fit=crop&w=800&q=80'
            ],
            'variants': [
                ('أسود مطفي', '#18181b', 'M', 4),
                ('أسود مطفي', '#18181b', 'L', 8),
                ('أسود مطفي', '#18181b', 'XL', 6),
                ('أسود مطفي', '#18181b', 'XXL', 3),
                ('كحلي داكن', '#0f172a', 'M', 3),
                ('كحلي داكن', '#0f172a', 'L', 6),
                ('كحلي داكن', '#0f172a', 'XL', 4)
            ]
        },
        {
            'name': 'تيشيرت رجالي أوفر سايز بيسيك',
            'slug': 'mens-oversized-basic-tshirt',
            'category': 'summer',
            'base_price': 13.00,
            'discount_price': 9.99,
            'sku': 'WQ-TS-009',
            'material': 'قطن ثقيل عالي الجودة 240 غرام',
            'fit': 'أوفر سايز (Oversized Fit)',
            'season': 'صيفي',
            'care_instructions': 'غسيل آلي بماء بارد، كي على الوجه الخلفي',
            'is_featured': 1,
            'is_new': 1,
            'is_bestseller': 1,
            'is_offer': 1,
            'description': 'تيشيرت شبابي عصري بقصة أوفر سايز المريحة والدارجة. مصنوع من القطن النقي عالي الكثافة ليمنحك إطلالة كاجوال مميزة تدوم طويلاً.',
            'images': [
                'https://images.unsplash.com/photo-1521572267360-ee0c2909d518?auto=format&fit=crop&w=800&q=80',
                'https://images.unsplash.com/photo-1581655353564-df123a1eb820?auto=format&fit=crop&w=800&q=80'
            ],
            'variants': [
                ('أبيض ناصع', '#ffffff', 'M', 10),
                ('أبيض ناصع', '#ffffff', 'L', 12),
                ('أبيض ناصع', '#ffffff', 'XL', 8),
                ('أسود فحمي', '#121212', 'M', 10),
                ('أسود فحمي', '#121212', 'L', 14),
                ('أسود فحمي', '#121212', 'XL', 9),
                ('بيج رملي', '#e5dcc5', 'M', 6),
                ('بيج رملي', '#e5dcc5', 'L', 8)
            ]
        },
        {
            'name': 'قميص كتان صيفي مريح',
            'slug': 'mens-linen-summer-shirt',
            'category': 'shirts',
            'base_price': 22.00,
            'discount_price': 16.99,
            'sku': 'WQ-SH-010',
            'material': 'كتان طبيعي 100%',
            'fit': 'ريلاكسد فيت (Relaxed Fit)',
            'season': 'صيفي',
            'care_instructions': 'غسيل يدوي أو خفيف، يفضل تركه يجف طبيعياً',
            'is_featured': 0,
            'is_new': 1,
            'is_bestseller': 0,
            'is_offer': 1,
            'description': 'قميص كتان خفيف ومثالي للأجواء الصيفية الحارة. يمنحك برودة وانتعاشاً فائقين مع إطلالة أنيقة وعفوية على البحر والمشاوير الصيفية.',
            'images': [
                'https://images.unsplash.com/photo-1603252109303-2751441dd157?auto=format&fit=crop&w=800&q=80',
                'https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?auto=format&fit=crop&w=800&q=80'
            ],
            'variants': [
                ('أبيض عاجي', '#fafaf9', 'M', 6),
                ('أبيض عاجي', '#fafaf9', 'L', 8),
                ('أبيض عاجي', '#fafaf9', 'XL', 5),
                ('سماوي فاتح', '#bae6fd', 'M', 5),
                ('سماوي فاتح', '#bae6fd', 'L', 7),
                ('سماوي فاتح', '#bae6fd', 'XL', 4),
                ('بيج طبيعي', '#d6c7b2', 'M', 4),
                ('بيج طبيعي', '#d6c7b2', 'L', 6)
            ]
        }
    ]

    for p in demo_products:
        cat_id = cat_map.get(p['category'])
        prod_row = cursor.execute("SELECT id FROM products WHERE slug = ?", (p['slug'],)).fetchone()
        if not prod_row:
            cursor.execute('''
            INSERT INTO products (
                category_id, name, slug, description, base_price, discount_price, sku,
                material, fit, season, care_instructions,
                is_featured, is_new, is_bestseller, is_offer, is_published
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ''', (
                cat_id, p['name'], p['slug'], p['description'], p['base_price'], p['discount_price'], p['sku'],
                p['material'], p['fit'], p['season'], p['care_instructions'],
                p['is_featured'], p['is_new'], p['is_bestseller'], p['is_offer']
            ))
            product_id = cursor.lastrowid
        else:
            product_id = prod_row['id']

        # Seed Images
        cursor.execute("DELETE FROM product_images WHERE product_id = ?", (product_id,))
        for idx, img_url in enumerate(p['images']):
            cursor.execute('''
            INSERT INTO product_images (product_id, image_url, is_primary, sort_order)
            VALUES (?, ?, ?, ?)
            ''', (product_id, img_url, 1 if idx == 0 else 0, idx))

        # Seed Variants with Stock
        cursor.execute("DELETE FROM product_variants WHERE product_id = ?", (product_id,))
        for color_name, color_hex, size_name, stock in p['variants']:
            sku_var = f"{p['sku']}-{size_name}"
            cursor.execute('''
            INSERT INTO product_variants (product_id, color_name, color_hex, size_name, stock_quantity, sku_variant)
            VALUES (?, ?, ?, ?, ?, ?)
            ''', (product_id, color_name, color_hex, size_name, stock, sku_var))

    # 7. Seed Demo Product Reviews
    first_prod = cursor.execute("SELECT id FROM products LIMIT 1").fetchone()
    if first_prod:
        pid = first_prod['id']
        reviews = [
            ('أحمد الزعبي', 5, 'خامة ممتازة جداً والمقاس مضبوط 100%، شكراً متجر وقار وأهل السلط على التعامل الراقي!', 1),
            ('عمر الحياري', 5, 'وصلني القميص خلال 24 ساعة في السلط، تغليف فخم وجودة عالية تضاهي الماركات العالمية.', 1),
            ('طارق الخريسات', 4, 'الخياطة نظيفة واللون فخم جداً. تجربة تسوق ممتازة والدفع عند الاستلام مريح.', 1)
        ]
        for cname, rating, comm, approved in reviews:
            cursor.execute('''
            INSERT OR IGNORE INTO product_reviews (product_id, customer_name, rating, comment, is_approved)
            VALUES (?, ?, ?, ?, ?)
            ''', (pid, cname, rating, comm, approved))

    conn.commit()
    if is_postgres():
        reset_postgres_sequences(conn)
    conn.close()
    print("Database seeding completed successfully for Waqar Store!")

if __name__ == '__main__':
    seed_all()

