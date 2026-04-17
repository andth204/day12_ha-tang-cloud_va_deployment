"""
Mock LLM — dùng chung cho tất cả ví dụ.
Không cần API key thật. Trả lời giả lập để focus vào deployment concept.
"""
import time
import random


MOCK_RESPONSES = {
    "default": [
        "Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.",
        "Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.",
        "Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.",
    ],
    "docker": ["Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"],
    "deploy": ["Deployment là quá trình đưa code từ máy bạn lên server để người khác dùng được."],
    "health": ["Agent đang hoạt động bình thường. All systems operational."],
    "hello": ["Xin chào! Tôi là AI agent. Bạn cần giúp gì?"],
    "jwt": ["JWT (JSON Web Token) là chuẩn mở để truyền thông tin an toàn giữa các bên dưới dạng JSON object."],
    "rate": ["Rate limiting giúp bảo vệ API khỏi bị lạm dụng bằng cách giới hạn số request mỗi user."],
    "scale": ["Scaling là khả năng tăng capacity để phục vụ nhiều user hơn, thường qua horizontal scaling."],
    "redis": ["Redis là in-memory data store, thường dùng cho caching, session storage, và rate limiting."],
    "microservice": ["Microservices là kiến trúc chia app thành các service nhỏ, độc lập, dễ scale riêng lẻ."],
}


def ask(question: str, delay: float = 0.1) -> str:
    """
    Mock LLM call với delay giả lập latency thật.
    """
    time.sleep(delay + random.uniform(0, 0.05))  # simulate API latency

    question_lower = question.lower()
    for keyword, responses in MOCK_RESPONSES.items():
        if keyword in question_lower:
            return random.choice(responses)

    return random.choice(MOCK_RESPONSES["default"])


def ask_stream(question: str):
    """
    Mock streaming response — yield từng token.
    """
    response = ask(question)
    words = response.split()
    for word in words:
        time.sleep(0.05)
        yield word + " "
