import os
import re
import json
from typing import Dict, Any, List, Tuple, Optional

# Russian stop words for filtering insignificant words during matching
STOP_WORDS = {
    "и", "в", "во", "не", "что", "он", "на", "я", "с", "со", "как", "а", "то", "все",
    "она", "так", "его", "но", "да", "ты", "к", "у", "же", "вы", "за", "бы", "по",
    "только", "ее", "мне", "было", "вот", "от", "меня", "еще", "нет", "о", "из", "ему",
    "теперь", "когда", "даже", "ну", "вдруг", "ли", "если", "уже", "или", "ни", "быть",
    "был", "него", "до", "вас", "нибудь", "опять", "уж", "вам", "ведь", "там", "потом",
    "себя", "ничего", "ей", "может", "они", "тут", "где", "есть", "надо", "ней", "для",
    "мы", "тебя", "их", "чем", "была", "сам", "чтоб", "без", "будто", "чего", "раз",
    "тоже", "себе", "под", "будет", "ж", "тогда", "кто", "этот", "того", "потому",
    "этого", "какой", "совсем", "ним", "здесь", "этом", "один", "почти", "мой", "тем",
    "чтобы", "нее", "сейчас", "были", "куда", "зачем", "всех", "никогда", "можно", "при",
    "наконец", "два", "об", "другой", "хоть", "после", "над", "больше", "тот", "через",
    "эти", "нас", "про", "всего", "них", "какая", "много", "разве", "три", "эту", "моя",
    "впрочем", "хорошо", "свою", "этой", "перед", "иногда", "лучше", "чуть", "том",
    "нельзя", "такой", "им", "более", "всегда", "конечно", "всю", "между", "наш", "наша",
    "нашей", "нашем", "наших", "какой", "какая", "какое", "какие", "ли", "это"
}

def clean_tokens(text: str) -> List[str]:
    words = re.findall(r"[a-zA-Zа-яА-Я0-9_-]+", text.lower())
    tokens = []
    for w in words:
        if len(w) <= 2 or w in STOP_WORDS:
            continue
        # simple stemming: cut off endings for Russian words
        stem = w
        if re.search(r"[а-яА-Я]", w):
            stem = re.sub(r"(ов|ев|ей|ами|ями|ом|ем|ам|ям|ах|ях|ую|юю|ое|ее|ие|ые|ого|его|ому|ему|ым|им|ой|ей|ью|а|я|о|е|и|ы|у|ю|ь)$", "", w)
            if len(stem) < 3:
                stem = w
        tokens.append(stem)
    return tokens

def split_into_sentences(text: str) -> List[str]:
    # Split by periods, exclamation marks, question marks, newlines
    raw_sentences = re.split(r"(?<=[.!?\n])\s+", text)
    cleaned = []
    for s in raw_sentences:
        st = s.strip()
        if len(st) > 10:
            cleaned.append(st)
    return cleaned

def generate_local_answer(question: str, context: str) -> Dict[str, Any]:
    """
    Deterministic rule-based / semantic extraction answering engine.
    Guarantees strict compliance with the project requirements:
    - answer based strictly on context
    - extract quotes from context
    - confidence rating
    - sets needs_review=True if context is insufficient
    """
    if not context or not context.strip():
        return {
            "answer": "Данных недостаточно для ответа на этот вопрос.",
            "sources": [],
            "confidence": "low",
            "needs_review": True
        }

    q_tokens = clean_tokens(question)
    if not q_tokens:
        return {
            "answer": "Вопрос не содержит ключевых слов для поиска.",
            "sources": [],
            "confidence": "low",
            "needs_review": True
        }

    sentences = split_into_sentences(context)
    if not sentences:
        sentences = [context.strip()]

    scored_sentences: List[Tuple[float, str]] = []
    for sentence in sentences:
        s_tokens = clean_tokens(sentence)
        if not s_tokens:
            continue

        matched_q_tokens = set()
        match_count = 0
        for qt in q_tokens:
            for st in s_tokens:
                if qt in st or st in qt:
                    matched_q_tokens.add(qt)
                    match_count += 1
                    break

        coverage = len(matched_q_tokens) / max(len(q_tokens), 1)
        score = (coverage * 3.0) + (match_count * 0.5)

        if coverage > 0.25 or match_count >= 2:
            scored_sentences.append((score, sentence))

    scored_sentences.sort(key=lambda x: x[0], reverse=True)

    if not scored_sentences:
        return {
            "answer": "В предоставленных материалах недостаточно данных для ответа на этот вопрос.",
            "sources": [],
            "confidence": "low",
            "needs_review": True
        }

    best_score, best_sentence = scored_sentences[0]

    # If the score is too low, we flag it as insufficient data
    if best_score < 1.0:
        return {
            "answer": "В материалах базы знаний нет точной информации по данному вопросу.",
            "sources": [],
            "confidence": "low",
            "needs_review": True
        }

    # Gather top relevant sentences (up to 2)
    selected_sentences = [best_sentence]
    for sc, sent in scored_sentences[1:3]:
        if sent not in selected_sentences and sc >= 1.0:
            selected_sentences.append(sent)

    answer_text = " ".join(selected_sentences)
    sources = [{"quote": sent} for sent in selected_sentences]

    confidence = "high" if best_score >= 2.0 else "medium"

    return {
        "answer": answer_text,
        "sources": sources,
        "confidence": confidence,
        "needs_review": False
    }

def answer_with_sources(question: str, context: str) -> Dict[str, Any]:
    """
    Main entry point for answering questions with sources.
    Uses LLM if OPENAI_API_KEY is configured, otherwise uses local deterministic engine.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key and os.getenv("USE_OPENAI", "false").lower() in ("true", "1", "yes"):
        try:
            import openai
            client = openai.OpenAI(api_key=api_key)
            prompt = (
                f"Ты — корпоративный ассистент базы знаний. Отвечай ТОЛЬКО на основе предоставленного контекста.\n"
                f"Правила:\n"
                f"1. Если контекст не содержит точного ответа или требует домыслов, укажи confidence='low', needs_review=true, "
                f"sources=[], и ответ 'Данных недостаточно для ответа на этот вопрос.'\n"
                f"2. Если ответ есть, приведи точные цитаты в 'sources' (массив {{'quote': string}}), confidence='high' или 'medium', needs_review=false.\n"
                f"3. Формат ответа строго JSON с ключами: answer (строка), sources (массив объектов с полем quote), confidence ('high'|'medium'|'low'), needs_review (boolean).\n\n"
                f"Контекст:\n{context}\n\n"
                f"Вопрос:\n{question}"
            )
            resp = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": "You are a factual knowledge assistant. Output ONLY valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.0
            )
            data = json.loads(resp.choices[0].message.content)
            # Ensure valid structure
            if "answer" in data and "sources" in data and "confidence" in data and "needs_review" in data:
                return {
                    "answer": str(data["answer"]),
                    "sources": [{"quote": str(s.get("quote", ""))} for s in data["sources"] if "quote" in s],
                    "confidence": str(data["confidence"]),
                    "needs_review": bool(data["needs_review"])
                }
        except Exception:
            # Fall back to local engine if OpenAI call fails
            pass

    return generate_local_answer(question, context)
