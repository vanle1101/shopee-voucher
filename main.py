"""
Telegram Deal/Voucher Real-Time Monitor từ noti.sale (Hướng 2 - Không cần điện thoại)
Tự động quét Real-Time các bài Post & Deal mới nhất từ noti.sale và bắn sang Telegram Channel.
"""

import os
import sys
import json
import re
import time
import html as html_lib
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

# Cấu hình encoding UTF-8 cho Windows Terminal để in tiếng Việt chuẩn
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Tải biến môi trường từ .env
load_dotenv(encoding="utf-8")

# Thiết lập logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("NotiMonitor")

# Cấu hình từ môi trường
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()
PRIVATE_CHAT_ID = os.getenv("PRIVATE_CHAT_ID", "").strip()
TEST_DEAL_ID = os.getenv("TEST_DEAL_ID", "38298").strip()

POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "15"))
ENABLE_POST_MONITOR = os.getenv("ENABLE_POST_MONITOR", "True").lower() in ["true", "1", "yes"]
ENABLE_DEAL_MONITOR = os.getenv("ENABLE_DEAL_MONITOR", "True").lower() in ["true", "1", "yes"]

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")

# User-Agent giả lập trình duyệt thật
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "vi,en-US;q=0.9,en;q=0.8",
    "Referer": "https://noti.sale/",
    "Sec-Ch-Ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1"
}


# ==============================================================================
# QUẢN LÝ TRẠNG THÁI (STATE / SEQUENTIAL IDS)
# ==============================================================================

def load_state() -> Dict[str, Any]:
    """Đọc file state.json lưu trữ ID bài viết và deal gần nhất."""
    default_state = {
        "last_post_id": 47448,
        "last_deal_id": 40555,
        "sent_items": [],
        "last_updated": None
    }
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in default_state.items():
                    if k not in data:
                        data[k] = v
                return data
        except Exception as e:
            logger.warning(f"Không thể đọc file state.json: {e}")
    return default_state


def save_state(state: Dict[str, Any]) -> None:
    """Ghi dữ liệu trạng thái vào file state.json."""
    state["last_updated"] = datetime.now().isoformat()
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Lỗi khi ghi state.json: {e}")


def is_item_sent(item_type: str, item_id: int | str, state: Dict[str, Any]) -> bool:
    """Kiểm tra một item (post:id hoặc deal:id) đã được gửi chưa."""
    item_key = f"{item_type}:{item_id}"
    return item_key in state.get("sent_items", [])


def mark_item_sent(item_type: str, item_id: int | str, state: Dict[str, Any]) -> None:
    """Đánh dấu một item đã gửi và cập nhật last ID."""
    item_key = f"{item_type}:{item_id}"
    if item_key not in state.get("sent_items", []):
        state.setdefault("sent_items", []).append(item_key)
    
    # Cập nhật last ID tương ứng
    int_id = int(item_id)
    if item_type == "post" and int_id > state.get("last_post_id", 0):
        state["last_post_id"] = int_id
    elif item_type == "deal" and int_id > state.get("last_deal_id", 0):
        state["last_deal_id"] = int_id

    save_state(state)


# ==============================================================================
# HÀM XỬ LÝ DỮ LIỆU & LÀM SẠCH TEXT
# ==============================================================================

def clean_text(text: str) -> str:
    """Làm sạch HTML entities, ký tự thừa và chuẩn hóa xuống dòng."""
    if not text:
        return ""
    text = html_lib.unescape(text)
    text = text.replace("\xa0", " ")
    lines = [line.strip() for line in text.split("\n")]
    cleaned = []
    prev_empty = False
    for line in lines:
        if not line:
            if not prev_empty:
                cleaned.append("")
                prev_empty = True
        else:
            cleaned.append(line)
            prev_empty = False
    return "\n".join(cleaned).strip()


def extract_voucher_and_expiry(text: str, published_time: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """
    Trích xuất mã voucher và hạn dùng / thời gian nếu có trong bài viết.
    Hỗ trợ cả các cú pháp nhập mã như: 'mã: XYZ', 'nhập mã: ABC', '=> VIPR1L5Pu130wiwQjspc'.
    """
    voucher_code: Optional[str] = None
    expiry: Optional[str] = None

    # Tìm mã voucher
    code_patterns = [
        r"(?:mã\s+nhập\s+tay|nhập\s+mã|áp\s+mã)[\s:：=>]+([A-Za-z0-9_-]{4,30})\b",
        r"(?:mã|code|voucher)[\s:：]+([A-Za-z0-9_-]{4,30})\b",
        r"🎟\s*(?:Mã|Code)[\s:：]+([A-Za-z0-9_-]{4,30})\b",
        r"\b([A-Z0-9]{5,20})\s*-\s*TAG\b",        # Dạng: HSBACKTOSCHOOLATK5H - TAG
        r"=>\s*([A-Za-z0-9]{8,25})\b",            # Dạng: => VIPR1L5Pu130wiwQjspc
        r"\b([A-Z0-9]{6,20})\s+giảm\s+\d+"         # Dạng: SPFKHAO50 giảm 50%
    ]
    def is_valid_voucher_code(code: str) -> bool:
        if not code or len(code) < 4 or code.isdigit():
            return False
        # Nếu toàn chữ thường và không có số thì chắc chắn là từ vựng bình thường (như 'shop', 'giam')
        if code.islower() and not any(c.isdigit() for c in code):
            return False
        # Danh sách từ vựng tiếng Việt / tiếng Anh thường gặp trong bài sale
        stopwords = {
            "SHOP", "SAN", "TOAN", "NGANH", "KHUNG", "DON", "GIA", "TOI", "DA",
            "NHIEU", "CUA", "BAN", "GIAM", "LUU", "HOT", "SALE", "DEAL", "SHOPEE",
            "LAZADA", "TIKTOK", "VOUCHER", "CODE", "MA", "FREE", "SHIP", "FREESHIP",
            "HAP", "DAN", "XEM", "NGAY", "CHOT", "THUONG", "HIEU", "CUOC", "MOI", "VIP"
        }
        if code.upper() in stopwords:
            return False
        # Mã voucher chuẩn phải có ít nhất 1 chữ số HOẶC là chuỗi in hoa từ 6 ký tự trở lên
        has_digit = any(c.isdigit() for c in code)
        if not has_digit and (len(code) < 6 or not code.isupper()):
            return False
        return True

    for pattern in code_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            if is_valid_voucher_code(candidate):
                voucher_code = candidate
                break

    # Tìm hạn dùng / khung giờ
    expiry_patterns = [
        r"(?:hạn(?:\s+dùng|\s+sử\s+dụng)?|áp\s+dụng\s+đến|kết\s+thúc\s+lúc)[\s:：]+([^\n\r.]+)",
        r"(?:khung\s+\d{1,2}[hH](?:\d{1,2})?|\b\d{1,2}[hH]\b|\b\d{1,2}H\s+hôm\s+nay\b)",
        r"⏰[\s:：]*([^\n\r.]+)"
    ]
    for pattern in expiry_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            exp_candidate = clean_text(match.group(1) if match.lastindex else match.group(0))
            if exp_candidate and len(exp_candidate) < 60:
                expiry = exp_candidate
                break

    return voucher_code, expiry


def extract_images(soup: BeautifulSoup, ld_data: Optional[Dict[str, Any]] = None) -> List[str]:
    """Trích xuất link ảnh bài viết từ ld+json, figure DOM hoặc meta og:image."""
    images: List[str] = []

    # 1. Từ ld+json
    if ld_data and "image" in ld_data:
        ld_images = ld_data["image"]
        if isinstance(ld_images, list):
            for img in ld_images:
                if isinstance(img, str) and img.startswith("http") and img not in images:
                    images.append(img)
        elif isinstance(ld_images, str) and ld_images.startswith("http") and ld_images not in images:
            images.append(ld_images)

    # 2. Từ DOM figure[itemprop="image"]
    fig = soup.find("figure", attrs={"itemprop": "image"})
    if fig:
        for img_tag in fig.find_all("img"):
            src = img_tag.get("src") or img_tag.get("data-src")
            if src:
                if "/_next/image?url=" in src:
                    m = re.search(r"url=([^&]+)", src)
                    if m:
                        import urllib.parse
                        real_url = urllib.parse.unquote(m.group(1))
                        if real_url.startswith("http") and real_url not in images:
                            images.append(real_url)
                elif src.startswith("http") and src not in images:
                    images.append(src)

    # 3. Meta og:image
    if not images:
        og_img = soup.find("meta", property="og:image")
        if og_img and og_img.get("content"):
            u = og_img["content"]
            if u.startswith("http") and "opengraph-image" not in u:
                images.append(u)

    return images


# ==============================================================================
# HÀM BÓC TÁCH DỮ LIỆU TỔNG QUÁT (POST & DEAL)
# ==============================================================================

def parse_item(html_content: str, item_type: str, item_id: int | str) -> Optional[Dict[str, Any]]:
    """
    Bóc tách dữ liệu bài viết (hỗ trợ cả post và deal):
    - Kiểm tra xem bài có tồn tại hay không
    - Bóc tách ld+json (SocialMediaPosting)
    - Lấy Title, Content, Images, Voucher code, Link
    """
    if not html_content:
        return None

    soup = BeautifulSoup(html_content, "html.parser")

    # Kiểm tra deal/post không tồn tại
    page_title = soup.find("title")
    title_text = page_title.get_text().strip() if page_title else ""
    if "không tồn tại" in title_text.lower() or title_text.startswith("404:") or title_text in ["Bài viết | Nô Tì", "Deal | Nô Tì"]:
        return {"not_found": True}

    # Bóc tách ld+json
    ld_data = None
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            d = json.loads(script.string or script.get_text() or "{}")
            if isinstance(d, dict) and d.get("@type") == "SocialMediaPosting":
                ld_data = d
                break
        except Exception:
            pass

    # Nếu không có ld+json và title mặc định -> chưa có bài viết
    if not ld_data and not soup.find(attrs={"itemprop": "articleBody"}):
        return {"not_found": True}

    item_url = f"https://noti.sale/{item_type}/{item_id}"

    # 1. Lấy Tiêu đề
    title = ""
    if ld_data and ld_data.get("headline"):
        title = ld_data["headline"].strip()
    if not title:
        og_t = soup.find("meta", property="og:title")
        if og_t and og_t.get("content"):
            title = og_t["content"].strip()
    if not title and title_text:
        title = title_text.replace(" | Nô Tì", "").strip()

    # 2. Lấy Nội dung (Content)
    content = ""
    body_elem = soup.find(attrs={"itemprop": "articleBody"})
    if body_elem:
        for tag in body_elem(["script", "style"]):
            tag.decompose()
        paragraphs = []
        for p in body_elem.find_all("p"):
            t = p.get_text().strip()
            if t:
                paragraphs.append(t)
        if paragraphs:
            first_p = paragraphs[0]
            if not title or title.startswith(first_p[:30]) or first_p.startswith(title[:30]):
                title = first_p
                content = "\n\n".join(paragraphs[1:])
            else:
                content = "\n\n".join(paragraphs)

    if not content and ld_data and ld_data.get("articleBody"):
        raw = ld_data["articleBody"]
        lines = [l.strip() for l in raw.split("\n") if l.strip()]
        if lines:
            if not title:
                title = lines[0]
                content = "\n\n".join(lines[1:])
            else:
                content = "\n\n".join(lines)
        else:
            content = raw

    title = clean_text(title)
    content = clean_text(content)

    # 3. Lấy ảnh
    images = extract_images(soup, ld_data)

    # 4. Lấy ngày đăng
    pub_time = ld_data.get("datePublished") if ld_data else None

    # 5. Voucher & Expiry
    v_code, exp = extract_voucher_and_expiry(f"{title}\n{content}", pub_time)

    item_info = {
        "type": item_type,
        "id": str(item_id),
        "url": item_url,
        "title": title or f"{item_type.capitalize()} #{item_id}",
        "content": content,
        "images": images,
        "primary_image": images[0] if images else None,
        "voucher_code": v_code,
        "expiry": exp,
        "published_time": pub_time
    }

    return item_info


def fetch_item(item_type: str, item_id: int | str, timeout: int = 15) -> Optional[Dict[str, Any]]:
    """Tải và bóc tách một bài viết theo type (post/deal) và id."""
    url = f"https://noti.sale/{item_type}/{item_id}"
    try:
        resp = requests.get(url, headers=BROWSER_HEADERS, timeout=timeout)
        if resp.status_code == 200:
            parsed = parse_item(resp.text, item_type, item_id)
            if parsed and not parsed.get("not_found"):
                return parsed
        return None
    except Exception as e:
        logger.debug(f"Lỗi fetch {url}: {e}")
        return None


# ==============================================================================
# HÀM GỬI TELEGRAM
# ==============================================================================

def format_telegram_message(item: Dict[str, Any]) -> str:
    """Định dạng bài viết gửi Telegram (đã bỏ link noti.sale theo yêu cầu)."""
    header = "🔥 VOUCHER MỚI" if item["type"] == "deal" else "📢 THÔNG BÁO SĂN SALE"
    parts = [
        header,
        "",
        item["title"],
        ""
    ]
    if item.get("content"):
        parts.append(item["content"])

    if item.get("voucher_code"):
        parts.append("")
        parts.append(f"🎟 Mã: {item['voucher_code']}")

    if item.get("expiry"):
        parts.append("")
        parts.append(f"⏰ Hạn: {item['expiry']}")

    return "\n".join(parts).strip()


def send_telegram(item: Dict[str, Any], chat_id: str, fallback_chat_id: Optional[str] = None) -> bool:
    """Gửi bài viết (ảnh + text) sang Telegram."""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN chưa được cấu hình!")
        return False

    caption = format_telegram_message(item)
    img_url = item.get("primary_image")

    def _do_send(target):
        if img_url:
            # Gửi ảnh kèm caption nếu <= 1024 ký tự
            if len(caption) <= 1024:
                res = requests.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                    json={"chat_id": target, "photo": img_url, "caption": caption},
                    timeout=25
                ).json()
                if res.get("ok"):
                    return True
            # Nếu dài hơn 1024 ký tự, gửi ảnh riêng rồi gửi text
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                json={"chat_id": target, "photo": img_url, "caption": caption[:150] + "..."},
                timeout=25
            )
        # Gửi full text qua sendMessage
        res = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": target, "text": caption[:4000], "disable_web_page_preview": False},
            timeout=25
        ).json()
        return bool(res.get("ok"))

    try:
        ok = _do_send(chat_id)
        if not ok and fallback_chat_id:
            logger.warning(f"Gửi vào {chat_id} thất bại, thử fallback vào {fallback_chat_id}...")
            ok = _do_send(fallback_chat_id)
        return ok
    except Exception as e:
        logger.error(f"Ngoại lệ khi gửi Telegram: {e}")
        return False


# ==============================================================================
# HÀM THỰC THI CHU KỲ POLLING REAL-TIME (HƯỚNG 2)
# ==============================================================================

def poll_once(state: Dict[str, Any]) -> int:
    """
    Thực hiện 1 chu kỳ quét:
    - Quét bài Post tiếp theo (last_post_id + 1, +2, ...)
    - Quét Deal tiếp theo (last_deal_id + 1, +2, ...)
    Trả về số lượng bài viết mới được phát hiện và gửi đi.
    """
    sent_count = 0

    # 1. Quét Post mới
    if ENABLE_POST_MONITOR:
        current_post_id = state.get("last_post_id", 47448)
        check_id = current_post_id + 1
        misses = 0
        max_misses = 6  # Bỏ qua tối đa 6 ID trống liên tiếp (do bài nháp hoặc admin xoá)

        while misses < max_misses:
            post = fetch_item("post", check_id)
            if post:
                logger.info(f"🎉 PHÁT HIỆN POST MỚI #{check_id}: {post['title'][:60]}...")
                if post.get("voucher_code"):
                    logger.info(f"   🎟 Phát hiện mã: {post['voucher_code']}")
                if post.get("primary_image"):
                    logger.info(f"   🖼 Link ảnh: {post['primary_image']}")
                
                # Gửi Telegram
                ok = send_telegram(post, CHAT_ID, fallback_chat_id=PRIVATE_CHAT_ID)
                if ok:
                    logger.info(f"   ✅ Đã gửi thành công Post #{check_id} sang Telegram!")
                    mark_item_sent("post", check_id, state)
                    sent_count += 1
                    time.sleep(1.5)  # Giãn cách 1.5s để tuân thủ rate-limit của Telegram
                misses = 0
            else:
                misses += 1
            check_id += 1

    # 2. Quét Deal mới
    if ENABLE_DEAL_MONITOR:
        current_deal_id = state.get("last_deal_id", 40555)
        check_id = current_deal_id + 1
        misses = 0
        max_misses = 6

        while misses < max_misses:
            deal = fetch_item("deal", check_id)
            if deal:
                logger.info(f"🎉 PHÁT HIỆN DEAL MỚI #{check_id}: {deal['title'][:60]}...")
                if deal.get("primary_image"):
                    logger.info(f"   🖼 Link ảnh: {deal['primary_image']}")
                
                ok = send_telegram(deal, CHAT_ID, fallback_chat_id=PRIVATE_CHAT_ID)
                if ok:
                    logger.info(f"   ✅ Đã gửi thành công Deal #{check_id} sang Telegram!")
                    mark_item_sent("deal", check_id, state)
                    sent_count += 1
                    time.sleep(1.5)
                misses = 0
            else:
                misses += 1
            check_id += 1

    return sent_count


def run_monitor(max_cycles: Optional[int] = None):
    """Vòng lặp giám sát Real-Time liên tục."""
    logger.info("=" * 65)
    logger.info("KHỞI ĐỘNG NOTI.SALE REAL-TIME MONITOR (HƯỚNG 2 - BỎ ĐIỆN THOẠI)")
    logger.info("=" * 65)
    logger.info(f"Target Channel : {CHAT_ID}")
    logger.info(f"Chu kỳ quét    : {POLL_INTERVAL_SECONDS} giây / lần")

    state = load_state()
    logger.info(f"Mốc Post ID hiện tại : #{state.get('last_post_id')}")
    logger.info(f"Mốc Deal ID hiện tại : #{state.get('last_deal_id')}")
    logger.info("-" * 65)

    cycles = 0
    try:
        while True:
            cycles += 1
            cur_post = state.get('last_post_id')
            cur_deal = state.get('last_deal_id')
            logger.info(f"[{datetime.now().strftime('%H:%M:%S')}] Đang quét (Post kế: #{cur_post+1}, Deal kế: #{cur_deal+1})...")

            sent = poll_once(state)
            if sent > 0:
                logger.info(f"-> Chu kỳ này đã gửi thành công {sent} bài viết mới!")

            if max_cycles and cycles >= max_cycles:
                logger.info(f"Đã hoàn thành {cycles} chu kỳ test. Dừng monitor.")
                break

            time.sleep(POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        logger.info("\nĐã nhận lệnh dừng (Ctrl+C). Lưu trạng thái và thoát an toàn.")
        save_state(state)


# ==============================================================================
# HÀM CHẠY TEST ĐƠN LẺ
# ==============================================================================

def test_single_item(item_type: str, item_id: str):
    """Test cào và gửi 1 bài viết/deal cụ thể."""
    logger.info(f"=== TEST THỦ CÔNG {item_type.upper()} #{item_id} ===")
    item = fetch_item(item_type, item_id)
    if not item:
        logger.error(f"Không tìm thấy hoặc không thể parse {item_type} #{item_id}")
        return
    logger.info(f"Tiêu đề: {item['title']}")
    logger.info(f"Ảnh    : {item.get('primary_image')}")
    logger.info(f"Mã     : {item.get('voucher_code')}")
    msg = format_telegram_message(item)
    print("\n--- PREVIEW TIN NHẮN ---")
    print(msg)
    print("------------------------\n")
    logger.info(f"Gửi sang Telegram {CHAT_ID}...")
    send_telegram(item, CHAT_ID, fallback_chat_id=PRIVATE_CHAT_ID)


def main():
    # Kiểm tra tham số dòng lệnh
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        item_id = sys.argv[2] if len(sys.argv) > 2 else TEST_DEAL_ID
        item_type = sys.argv[3] if len(sys.argv) > 3 else "deal"
        test_single_item(item_type, item_id)
    elif len(sys.argv) > 1 and sys.argv[1] == "once":
        # Chạy 1 chu kỳ duy nhất
        state = load_state()
        poll_once(state)
    elif len(sys.argv) > 1 and sys.argv[1] == "cycles":
        count = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        run_monitor(max_cycles=count)
    else:
        # Chế độ Monitor mặc định
        run_monitor()


if __name__ == "__main__":
    main()
