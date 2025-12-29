# 🤖 Hantubot - 한국 주식 자동매매 시스템

> **프로덕션급 알고리즘 트레이딩 시스템 | 한국투자증권 API 기반**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Production-success.svg)](https://github.com)

---

## 📌 목차

1. [프로젝트 소개](#-프로젝트-소개)
2. [주요 기능](#-주요-기능)
3. [설치 및 실행](#-설치-및-실행)
4. [문서 가이드](#-문서-가이드)
5. [면책 조항](#-면책-조항)

---

## 🎯 프로젝트 소개

Hantubot은 한국투자증권 API를 활용한 **완전 자동화된 알고리즘 트레이딩 시스템**입니다.

### ✨ 핵심 특징

- 🏢 **프로덕션급 안정성**: 중앙화된 주문 관리, 동시성 제어, 에러 처리
- ⏰ **시간대별 전략 관리**: 09:00 시초가 청산, 전략별 자동 청산
- 📊 **레짐 기반 매매**: 시장 상황(상승/중립/하락)에 따른 동적 파라미터 조정
- 📱 **Discord 실시간 알림**: 매수/매도 체결, 잔고, 손익률 상세 알림
- 📚 **유목민 공부법**: 장 마감 후 자동 데이터 수집 및 AI 분석
- 🎨 **GUI 컨트롤러**: PySide6 기반 직관적인 인터페이스

---

## 🚀 주요 기능

### 1. 지능형 시간 관리
- **09:00**: 시초가 청산 (최우선)
- **09:00-09:30**: Opening Breakout 전략 (갭 상승 + 거래량)
- **09:30-14:50**: Volume Spike 전략 (거래량 급증 추격)
- **15:03**: Closing Price 전략 (종가 매매)
- **15:30**: 장 마감 후 데이터 수집 및 리포팅

### 2. 레짐 기반 동적 매매
시장 상황(상승/중립/하락)에 따라 익절/손절 폭과 매수 조건을 자동으로 조절합니다.

### 3. 유목민 공부법 (자동 학습)
매일 장 마감 후 상한가 및 대량 거래 종목을 수집하고, **Gemini AI**가 상승 이유를 요약해줍니다.

---

## 💻 설치 및 실행

### 1. 설치
```bash
git clone https://github.com/PARK-Yunjae/hantubot.git
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 설정
`configs/.env.example`을 복사하여 `.env`를 만들고 API 키를 입력하세요.

### 3. 실행
```bash
python run.py
# 또는 start_hantubot.bat 더블클릭
```

> 자세한 내용은 **[📘 통합 매뉴얼](docs/MANUAL.md)**을 참고하세요.

---

## 📚 문서 가이드

프로젝트의 모든 문서는 `docs/` 폴더에 정리되어 있습니다.

### 📘 [MANUAL.md](docs/MANUAL.md)
**설치부터 실행까지 한 번에!**
- 환경 설정, API 발급, 이메일/디스코드 알림 설정
- EXE 배포 방법

### 🐍 [PYTHON_GUIDE.md](docs/PYTHON_GUIDE.md)
**코드 구조를 이해하고 싶다면?**
- 파이썬 기초 문법 복습
- Hantubot 아키텍처 및 데이터 흐름
- 나만의 커스텀 전략 만드는 법

### 🕯️ [NOMAD_STUDY.md](docs/NOMAD_STUDY.md)
**주식 공부를 자동으로!**
- 유목민 공부법 소개
- AI 요약 및 대시보드 사용법

---

## ⚠️ 면책 조항

**중요: 반드시 읽어주세요!**

1. **투자 책임**: 이 소프트웨어를 사용한 모든 거래의 손익은 사용자 본인의 책임입니다.
2. **손실 위험**: 주식 투자는 원금 손실의 위험이 있습니다.
3. **테스트 권장**: 실전 투자 전 충분한 모의투자 테스트를 권장합니다.
4. **법적 책임**: 개발자는 이 소프트웨어 사용으로 인한 어떠한 손실에 대해서도 법적 책임을 지지 않습니다.

---

## 📞 문의

- **GitHub Issues**: [Issues 페이지](https://github.com/PARK-Yunjae/hantubot/issues)

---

<div align="center">

**⭐ 도움이 되셨다면 Star를 눌러주세요! ⭐**

</div>
