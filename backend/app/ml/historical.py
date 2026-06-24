"""Historical-incident similarity search + clustering (TF-IDF + KMeans).

Backs the agent's ``search_historical_incidents`` tool (Phase 5) and groups prior incidents.
"""

from __future__ import annotations

from dataclasses import dataclass

from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import HistoricalIncident


@dataclass
class HistoricalMatch:
    historical_incident_id: str
    score: float
    incident_type: str
    title: str
    root_cause: str
    remediation: str
    cluster: int


class HistoricalIndex:
    """TF-IDF index over historical incidents with KMeans cluster labels."""

    def __init__(self, n_clusters: int = 5) -> None:
        self.n_clusters = n_clusters
        self._vectorizer: TfidfVectorizer | None = None
        self._matrix = None
        self._ids: list[str] = []
        self._meta: dict[str, HistoricalIncident] = {}
        self._clusters: dict[str, int] = {}

    def fit(self, session: Session) -> HistoricalIndex:
        rows = list(session.execute(select(HistoricalIncident)).scalars())
        if not rows:
            return self
        self._ids = [r.historical_incident_id for r in rows]
        self._meta = {r.historical_incident_id: r for r in rows}
        texts = [r.searchable_text for r in rows]
        self._vectorizer = TfidfVectorizer(stop_words="english")
        self._matrix = self._vectorizer.fit_transform(texts)
        k = min(self.n_clusters, len(rows))
        if k >= 2:
            seed = get_settings().random_seed
            labels = KMeans(n_clusters=k, random_state=seed, n_init=10).fit_predict(self._matrix)
            self._clusters = dict(zip(self._ids, (int(x) for x in labels)))
        else:
            self._clusters = dict.fromkeys(self._ids, 0)
        return self

    def search(self, query: str, k: int = 5) -> list[HistoricalMatch]:
        if self._vectorizer is None or not self._ids:
            return []
        qv = self._vectorizer.transform([query])
        sims = cosine_similarity(qv, self._matrix)[0]
        ranked = sorted(zip(self._ids, sims), key=lambda x: x[1], reverse=True)[:k]
        out: list[HistoricalMatch] = []
        for hid, score in ranked:
            r = self._meta[hid]
            out.append(HistoricalMatch(
                historical_incident_id=hid, score=float(score),
                incident_type=r.incident_type, title=r.title, root_cause=r.root_cause,
                remediation=r.remediation, cluster=self._clusters.get(hid, 0),
            ))
        return out
