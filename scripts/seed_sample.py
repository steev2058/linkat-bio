from app.db import init_db, get_conn, utcnow


def run():
    init_db()
    with get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO users (tg_user_id, username, language, plan_type, created_at) VALUES (?,?,?,?,?)", (999001, 'demo_creator', 'ar', 'FREE', utcnow()))
        u = conn.execute("SELECT * FROM users WHERE tg_user_id=999001").fetchone()
        conn.execute(
            "INSERT OR IGNORE INTO pages (user_id, slug, display_name, bio, is_published, created_at, updated_at) VALUES (?,?,?,?,1,?,?)",
            (u['id'], 'demo-linkat', 'Demo Linkat', 'صفحة تجريبية من Linkat', utcnow(), utcnow())
        )
        p = conn.execute("SELECT * FROM pages WHERE user_id=?", (u['id'],)).fetchone()
        existing = conn.execute("SELECT COUNT(*) c FROM links WHERE page_id=?", (p['id'],)).fetchone()['c']
        if existing == 0:
            conn.execute(
                "INSERT INTO links (page_id, title, url, platform, position, is_active, created_at) VALUES (?,?,?,?,?,?,?)",
                (p['id'], 'Instagram', 'https://instagram.com', 'instagram', 1, 1, utcnow())
            )
            conn.execute(
                "INSERT INTO links (page_id, title, url, platform, position, is_active, created_at) VALUES (?,?,?,?,?,?,?)",
                (p['id'], 'YouTube', 'https://youtube.com', 'youtube', 2, 1, utcnow())
            )
        conn.execute("INSERT OR IGNORE INTO vouchers (code, plan_type, duration_days, is_active, created_at) VALUES ('LINKAT30', 'PRO_1', 30, 1, ?)", (utcnow(),))
        conn.execute("INSERT OR IGNORE INTO vouchers (code, plan_type, duration_days, is_active, created_at) VALUES ('LINKATPRO3', 'PRO_3', 90, 1, ?)", (utcnow(),))
    print('Seed complete: page /u/demo-linkat + vouchers LINKAT30/LINKATPRO3')


if __name__ == '__main__':
    run()
