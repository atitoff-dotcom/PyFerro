# 🏛️ PyFerro Project Rules & Architecture Guidelines

### 📜 Project Architecture Rules:
* **Release & Database Migrations:** Новый минорный релиз (например, `x.Y.0`) обязательно требует миграции базы данных, и мы должны генерировать код этой миграции.
* **Zero-Paranoia & Boundary Defense:** Никаких параноидальных проверок внутри доверенного контура (`isinstance`, `if x is None`, повторная валидация собственных структур). Валидация выполняется строго один раз на внешней границе (Untrusted Boundary). Внутри ядра доверяем собственным типам, инвариантам и контрактам.
