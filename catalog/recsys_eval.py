"""Đánh giá mô hình gợi ý sản phẩm trên bộ dữ liệu hành vi Retail Rocket (NFR07, FR18).

Thuật toán GIỐNG phần gợi ý trực tuyến trong catalog/services.py (cosine giữa các sản phẩm trên vectơ người dùng x sản phẩm,
trọng số xem=1, thêm giỏ=3, mua=5, trần 10 điểm cho mỗi cặp), so sánh với phương án dự phòng "sản phẩm phổ biến".

Quy trình: sắp xếp sự kiện theo thời gian, chia theo mốc thời gian (mặc định 80% đầu để huấn luyện, 20% sau để kiểm tra);
với mỗi người dùng có lịch sử huấn luyện đủ dài, sản phẩm "đúng" là các sản phẩm họ thêm vào giỏ hoặc mua ở giai đoạn kiểm tra;
gợi ý không lặp lại sản phẩm họ đã tương tác trong huấn luyện. Chỉ số: Precision@K, Recall@K, NDCG@K, HitRate@K.

Mô-đun này thuần Python, không phụ thuộc Django.
"""
import csv
import math
import random
from collections import defaultdict

WEIGHTS = {"view": 1, "addtocart": 3, "transaction": 5}
WEIGHT_CAP = 10
POSITIVE = ("addtocart", "transaction")


def load_events(path, max_rows=None):
    """Đọc events.csv của Retail Rocket (timestamp, visitorid, event, itemid, transactionid)."""
    events = []
    with open(path, newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f)):
            if max_rows and i >= max_rows:
                break
            ev = row["event"]
            if ev in WEIGHTS:
                events.append((int(row["timestamp"]), row["visitorid"], int(row["itemid"]), ev))
    events.sort()
    return events


def synthetic_events(n_users=1500, n_items=300, n_clusters=10, seed=7):
    """Dữ liệu giả lập để chạy thử khi chưa tải Retail Rocket: mỗi người dùng thích vài nhóm sản phẩm."""
    rng = random.Random(seed)
    per = n_items // n_clusters
    events, horizon = [], 10_000_000
    for u in range(n_users):
        likes = rng.sample(range(n_clusters), 2)
        for _ in range(rng.randint(8, 30)):
            t = rng.randint(0, horizon)      # sự kiện của các người dùng đan xen theo thời gian
            c = rng.choice(likes) if rng.random() < 0.85 else rng.randrange(n_clusters)
            item = c * per + min(int(rng.expovariate(1 / (per / 4))), per - 1)   # đuôi dài: vài sản phẩm rất phổ biến
            r = rng.random()
            ev = "view" if r < 0.8 else ("addtocart" if r < 0.94 else "transaction")
            events.append((t, f"u{u}", item, ev))
    return events


def split_by_time(events, ratio=0.8):
    events = sorted(events)
    cut = events[int(len(events) * ratio)][0]
    return [e for e in events if e[0] < cut], [e for e in events if e[0] >= cut]


def build_vectors(events):
    vec = defaultdict(lambda: defaultdict(float))
    for _, user, item, ev in events:
        vec[user][item] += WEIGHTS[ev]
    return {u: {i: min(w, WEIGHT_CAP) for i, w in d.items()} for u, d in vec.items()}


class PopularModel:
    """Phương án dự phòng: sản phẩm phổ biến theo tổng điểm tương tác."""
    name = "Phổ biến (dự phòng)"

    def fit(self, vec):
        score = defaultdict(float)
        for d in vec.values():
            for i, w in d.items():
                score[i] += w
        self.ranked = sorted(score, key=lambda i: (-score[i], i))
        return self

    def recommend(self, profile, k):
        out = []
        for i in self.ranked:
            if i not in profile:
                out.append(i)
                if len(out) == k:
                    break
        return out


class ItemCosineModel:
    """Gợi ý theo độ tương đồng cosine giữa các sản phẩm (giống catalog/services._item_scores)."""
    name = "Cosine theo hành vi (mô hình của website)"

    def __init__(self, max_neighbors=300):
        self.max_neighbors = max_neighbors     # giới hạn số người dùng xét cho mỗi sản phẩm để bảo đảm tốc độ

    def fit(self, vec):
        self.vec = vec
        norm, inv = defaultdict(float), defaultdict(list)
        for user, d in vec.items():
            for i, w in d.items():
                norm[i] += w * w
                inv[i].append(user)
        self.norm = {i: math.sqrt(v) for i, v in norm.items()}
        self.inv = {i: users[-self.max_neighbors:] for i, users in inv.items()}
        return self

    def recommend(self, profile, k, skip_user=None):
        score = defaultdict(float)
        for s, ws in profile.items():
            for user in self.inv.get(s, ()):
                if user == skip_user:
                    continue
                d = self.vec[user]
                a = d[s]
                for p, w in d.items():
                    if p == s or p in profile:
                        continue
                    score[p] += ws * a * w / (self.norm[s] * self.norm[p])
        return sorted(score, key=lambda p: (-score[p], p))[:k]


def metrics_at_k(recommended, relevant, k):
    hits = [1 if i in relevant else 0 for i in recommended[:k]]
    n = sum(hits)
    dcg = sum(h / math.log2(pos + 2) for pos, h in enumerate(hits))
    idcg = sum(1 / math.log2(pos + 2) for pos in range(min(len(relevant), k)))
    return {"precision": n / k, "recall": n / len(relevant), "ndcg": dcg / idcg if idcg else 0.0, "hit": 1.0 if n else 0.0}


def evaluate(events, k=10, ratio=0.8, min_history=3, max_users=2000, seed=1):
    train, test = split_by_time(events, ratio)
    vec = build_vectors(train)
    relevant = defaultdict(set)
    for _, user, item, ev in test:
        if ev in POSITIVE:
            relevant[user].add(item)
    users = [u for u in relevant if u in vec and len(vec[u]) >= min_history]
    random.Random(seed).shuffle(users)
    users = users[:max_users]
    models = [PopularModel().fit(vec), ItemCosineModel().fit(vec)]
    result = {"k": k, "train_events": len(train), "test_events": len(test), "train_users": len(vec),
              "eval_users": len(users), "models": {}}
    for m in models:
        acc = defaultdict(float)
        for u in users:
            rec = m.recommend(vec[u], k) if isinstance(m, PopularModel) else m.recommend(vec[u], k, skip_user=u)
            for name, val in metrics_at_k(rec, relevant[u], k).items():
                acc[name] += val
        n = max(1, len(users))
        result["models"][m.name] = {name: round(v / n, 5) for name, v in acc.items()}
    return result


def format_report(res):
    lines = [f"Đánh giá gợi ý sản phẩm (K={res['k']}): huấn luyện {res['train_events']} sự kiện / {res['train_users']} người dùng; "
             f"kiểm tra {res['test_events']} sự kiện; số người dùng đánh giá: {res['eval_users']}", ""]
    lines.append(f"{'Mô hình':<46}{'Precision@K':>12}{'Recall@K':>10}{'NDCG@K':>9}{'HitRate@K':>11}")
    for name, m in res["models"].items():
        lines.append(f"{name:<46}{m['precision']:>12.4f}{m['recall']:>10.4f}{m['ndcg']:>9.4f}{m['hit']:>11.4f}")
    return "\n".join(lines)
