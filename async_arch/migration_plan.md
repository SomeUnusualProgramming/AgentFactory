# Plan Migracji: AgentFactory Async Architecture

Ten dokument opisuje proces przejścia z sekwencyjnej architektury (`factory_boss.py`) na architekturę zdarzeniową (Event-Driven) opartą na `asyncio` i `Redis`.

## Faza 1: Przygotowanie Fundamentów (Infrastructure)

1.  **Instalacja Redis**
    -   Zainstaluj Redis server lokalnie lub uruchom w Dockerze: `docker run -d -p 6379:6379 redis`.
    -   Zainstaluj klienta Python: `pip install redis`.

2.  **Inicjalizacja Środowiska `uv`**
    -   Zainstaluj `uv`: `pip install uv` (lub wg instrukcji systemowej).
    -   Zainicjuj projekt: `uv init`.
    -   Dodaj zależności: `uv add redis jinja2 aiohttp`.

3.  **Implementacja StateManager**
    -   Wdróż klasę `RedisStateManager` (z pliku `async_arch/state_manager.py`).
    -   Cel: Zastąpienie pliku `blackboard.json` szybką pamięcią Redis.

## Faza 2: Rdzeń Asynchroniczny (Core Migration)

4.  **Refaktoryzacja Agentów (Wrapper)**
    -   Obecne agenty (`agent_analyst.py` itp.) są skryptami blokującymi.
    -   Krok: Opakuj wywołania `ollama.chat` w funkcje asynchroniczne (`async def`).
    -   Przykład: `await asyncio.to_thread(agent_analyst.run, ...)` jako tymczasowe rozwiązanie, docelowo użyj `ollama-python` w trybie async lub `aiohttp` do API.

5.  **Implementacja Orchestratora**
    -   Wdróż `AsyncOrchestrator` (z pliku `async_arch/orchestrator.py`).
    -   Zastąp logikę pętli w `factory_boss.py` wywołaniami `await asyncio.gather()`.

## Faza 3: Hybrydowe Generowanie (Optimization)

6.  **System Szablonów**
    -   Stwórz katalog `templates/` i przenieś powtarzalny kod (boilerplate Flask, setup.py) do plików `.j2`.
    -   Zaimplementuj `HybridGenerator` (z pliku `async_arch/hybrid_generator.py`).

7.  **Integracja z Agentem Deweloperem**
    -   Zmodyfikuj `agent_developer.py`, aby zamiast pisać cały plik od zera, otrzymywał wyrenderowany szablon i uzupełniał tylko luki.

## Faza 4: Pełne Przełączenie (Cutover)

8.  **Event Loop & Pub/Sub**
    -   Uruchom `AsyncOrchestrator` jako główny proces.
    -   Skonfiguruj nasłuchiwanie zdarzeń `TASK_COMPLETED` do logowania postępów w czasie rzeczywistym.

9.  **Testy Obciążeniowe**
    -   Uruchom generowanie złożonego projektu (np. "E-commerce platform"), który wymaga 5+ modułów.
    -   Zweryfikuj, czy moduły "Frontend" i "Backend" generują się równolegle (sprawdź logi czasowe).

## Priorytety

1.  **Asyncio**: Największy zysk wydajności (równoległość).
2.  **Redis**: Bezpieczeństwo danych przy równoległości.
3.  **Szablony**: Lepsza jakość kodu i mniejsze zużycie tokenów LLM.
4.  **uv**: Szybsze zarządzanie środowiskiem (można dodać na końcu).
