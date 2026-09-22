# 给 Spring / .NET 工程师的 Python 技术栈速通

> **读者定位**：熟悉 Spring Boot / Spring Cloud / .NET Core，但没写过 Python 的工程师。
> **目的**：让你能读懂、review 和调试本仓库（FlowForm）的后端代码，而不必先学一遍 Python。
> **写法**：全部用你已有的概念做对照，并**显式标出「看起来一样、其实完全不同」的地方**——
> 那些才是 review 时最容易误判的。

技术栈：Python 3.12 + FastAPI + SQLAlchemy 2.0 + Alembic + Pydantic v2。

---

## 0. 先建立三个直觉

在深入细节之前，先矫正三个最容易带偏判断的认知：

### ① Python 的 `@decorator` **不是** Java 的 `@Annotation`

这是最重要的一条。两者都写成 `@Xxx`，但本质完全不同：

| | Java / C# 注解 | Python 装饰器 |
|---|---|---|
| 是什么 | **元数据**，本身不做任何事 | **一个函数**，在定义时被调用，返回值**替换**被装饰的对象 |
| 何时生效 | 运行时由框架反射读取 | **导入模块时**立即执行 |
| 不写框架会怎样 | 注解被忽略，功能失效 | 等价于没写，函数保持原样 |

看这段本仓库的代码：

```python
@router.get("", response_model=Page[UserOut], summary="用户列表")
def list_users(db: DbSession, _: AdminUser, ...) -> dict:
    ...
```

Java 工程师会读成「给这个方法打了个 GET 标记，Spring 扫描到后注册路由」。
实际发生的是：

```python
# 等价于（示意）
def list_users(...): ...
list_users = router.get("", response_model=..., summary=...)(list_users)
```

`router.get(...)` **是一个函数调用**，它返回一个装饰器，装饰器把 `list_users`
包起来并**注册进路由表**，最后把 `list_users` 这个名字**重新绑定**成路由对象。

**对 review 的意义**：
- 装饰器顺序是有语义的（从下往上应用），和注解顺序无关
- 装饰器在 import 时执行 —— 所以**导入模块会有副作用**，这也是 FastAPI 注册路由的机制
- 你没法「跳过」装饰器，它不是可选的元数据

### ② 没有 IoC 容器，没有 Bean，没有组件扫描

Spring 启动时会扫描 `@Component`/`@Service`/`@Repository`，构造一个 Bean 图。
**FastAPI 里没有这些东西**。本仓库的分层纯粹是**目录约定**：

```
api/v1/users.py      ← 相当于 @RestController
services/user_service.py  ← 相当于 @Service（但没有任何注解）
models/org.py        ← 相当于 @Entity
schemas/org.py       ← 相当于 DTO
```

`user_service` 就是一个普通模块，`api` 层直接 `from app.services import user_service` 然后调函数。
没有构造注入、没有单例 Bean、没有 AOP 代理。

那依赖怎么传？看下一节。

### ③ 没有 `@Transactional`，事务靠**显式 commit**

这是 review 时第二个高频误判点。本仓库的服务方法长这样：

```python
def create(db: Session, payload: UserCreate, *, actor: User | None = None) -> User:
    ...
    db.add(user)
    db.flush()
    audit_service.record(db, ...)   # 只是 add，不 commit
    db.commit()                      # ← 事务边界在这里
    db.refresh(user)
    return user
```

**没有 `@Transactional`，没有 Spring 的自动回滚**。详见 §2.4，那里完整讲了这套模型的
事务语义以及它和 Spring 的差异。

---

## 1. 总对照表

把这张表当地图用，需要细节时再往下翻。

### 1.1 框架组件

| 你熟悉的 | 本仓库对应的 | 备注 |
|---|---|---|
| Spring Boot `@RestController` | `APIRouter` + 路径装饰器 | `app/api/v1/*.py` |
| Spring `@Service` | 普通模块里的函数 | `app/services/*.py`，**无注解** |
| Spring Data JPA `Repository` | SQLAlchemy `Session` + `select()` | 见 §2.2，我们**没有** Repository 接口层 |
| JPA `@Entity` | `Base` + `Mapped[...]` / `mapped_column` | `app/models/*.py` |
| Hibernate `Session` / `EntityManager` | SQLAlchemy `Session` | 名字一样，模型不同，见 §2.3 |
| DTO + Bean Validation `@Valid` | Pydantic `BaseModel` | `app/schemas/*.py` |
| `@ControllerAdvice` + `@ExceptionHandler` | `@app.exception_handler(...)` | `app/core/errors.py` |
| `HandlerInterceptor` / `Filter` | `@app.middleware("http")` / `Depends` | |
| `@Autowired` / 构造注入 | `Depends(...)` | **机制完全不同**，见 §1.3 |
| `application.yml` + `@Value` | `.env` + `pydantic-settings` | `app/core/config.py` |
| Flyway / Liquibase | **Alembic** | `alembic/` |
| springdoc-openapi | FastAPI **内置** | `/docs` 开箱可用 |
| Maven / Gradle | pip + `requirements.txt` | 见 §4.7 |
| JUnit 5 | pytest | `backend/tests/` |
| Mockito | `unittest.mock` / pytest fixture | |
| SLF4J + Logback | 标准库 `logging` | `app/main.py` 里配置 |
| Lombok `@Data` | 不需要 | Python 对象天然动态 |

### 1.2 .NET Core 对照

| 你熟悉的 | 本仓库对应的 |
|---|---|
| ASP.NET Core Controller | `APIRouter` |
| EF Core `DbContext` | SQLAlchemy `Session` |
| EF Core Migrations | Alembic |
| `appsettings.json` + `IOptions` | `.env` + `pydantic-settings` |
| `ILogger<T>` | `logging.getLogger(__name__)` |
| NuGet | pip |
| xUnit | pytest |
| `[FromBody]` 模型绑定 | Pydantic `BaseModel` |
| 内置 DI 容器 | `Depends` |

### 1.3 依赖注入：`Depends` ≠ `@Autowired`

Spring 的 DI：容器管生命周期（singleton/prototype/request），代理解决循环依赖，
`@Autowired` 把 Bean 塞进字段或构造器。

FastAPI 的 `Depends` 简单粗暴得多：**声明一个可调用对象，FastAPI 在每次请求时调用它，把返回值作为参数注入**。

```python
# backend/app/core/deps.py

def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db          # ← 生成器：yield 之前是「进入」，之后是「退出」
    finally:
        db.close()

DbSession = Annotated[Session, Depends(get_db)]

def get_current_user(db: DbSession, credentials: ...) -> User:
    ...
    return user       # 返回值会被注入到路由函数

CurrentUser = Annotated[User, Depends(get_current_user)]
```

路由里这样用：

```python
@router.get("/me", response_model=MeResponse)
def me(db: DbSession, user: CurrentUser) -> MeResponse:
    return auth_service.me(db, user)
```

**关键差异**：
- **没有容器**。`Depends(get_db)` 就是「调用 `get_db()`，把结果给我」
- **每次请求都重新执行**（除非显式 `use_cache=True` 且路径上重复出现，默认就是缓存的）
- **`yield` 依赖**是 Python 的生成器：`yield` 前 = 请求处理前的准备，`yield` 后 = 响应后的清理
  （等价于 `@PreDestroy` / `IDisposable`，但作用域是单个请求）
- **依赖可以嵌套**：`get_current_user` 自己又依赖 `DbSession`，FastAPI 递归解析
- **权限就是依赖**：`AdminUser = Annotated[User, Depends(require_admin)]`，
  函数体里 `raise ForbiddenError` 就是鉴权失败。没有 `@PreAuthorize` 那种注解式切面

> **Review 提示**：想看某个接口的完整依赖链，顺着参数的类型别名（`AdminUser`）
> 去 `core/deps.py` 找，别去找什么 Bean 配置类。

### 1.4 项目结构对照

```
Spring Boot 项目                    FlowForm 后端
────────────────────────────        ────────────────────────────
src/main/java/com/x/
├── controller/          ──────→   app/api/v1/          # 路由（薄，只做参数/权限/编排）
├── service/             ──────→   app/services/        # 业务逻辑 + 事务边界
├── repository/          ──────→   (无，直接用 Session)  # 见 §2.2
├── entity/              ──────→   app/models/          # ORM 实体
├── dto/                 ──────→   app/schemas/         # Pydantic DTO
├── config/              ──────→   app/core/            # 配置、安全、错误、常量
└── Application.java     ──────→   app/main.py          # 应用装配

src/main/resources/
├── application.yml      ──────→   backend/.env
└── db/migration/        ──────→   backend/alembic/versions/

src/test/java/           ──────→   backend/tests/
pom.xml / build.gradle   ──────→   backend/requirements.txt + pyproject.toml
```

**分层约束**（本仓库严格执行，review 时可据此判断代码放对位置没）：

```
api  →  services  →  models / db
```

- `core/` 是最底层，**不依赖** `models`（`core/policy.py` 用 `Protocol` 而不是导入 `User` —— 就是为了守住这条）
- `services/` 里不出现 `Request` / `HTTPException`（那是 `api/` 的事）
- 反向依赖（`models` 导入 `services`）是红线，Python 里会直接变成循环导入错误

---

## 2. FastAPI 详解

### 2.1 路由

```python
# backend/app/api/v1/users.py
router = APIRouter(prefix="/users", tags=["用户管理"])

@router.get("", response_model=Page[UserOut], summary="用户列表")
def list_users(
    db: DbSession,
    _: AdminUser,                                    # ← 权限：不是管理员的请求到这里已被拦掉
    paging: Annotated[PageParams, Depends()],
    keyword: Annotated[str | None, Query()] = None,
) -> dict:
    ...
```

对照 Spring：

| Spring | FastAPI |
|---|---|
| `@RequestMapping("/users")` 类级 | `APIRouter(prefix="/users")` |
| `@GetMapping` / `@PostMapping` | `@router.get` / `@router.post` |
| `@RequestBody UserCreate dto` | 参数类型是 Pydantic 模型即自动解析 body |
| `@RequestParam` / `@PathVariable` | 普通参数即 query；路径里的 `{user_id}` 对应的参数即 path |
| `@Valid` | **自动的**，Pydantic 模型声明即校验 |
| `ResponseEntity<T>` | `response_model=` + 返回普通对象 |
| `@ResponseStatus(CREATED)` | `status_code=status.HTTP_201_CREATED` |

**两个值得注意的点**：

1. **返回值不写 `return` 类型也能工作**，但本仓库坚持写 `-> dict` / `-> UserOut`，
   因为 ruff 会检查、人也需要。别把它当成 Spring 那种可选的文档注解。

2. **`response_model` 做的是出参过滤**，等价于 Spring 里返回 DTO 而不是 Entity。
   即使函数返回的是 ORM 对象，`response_model` 也只输出声明的字段 ——
   **这是防止密码哈希等敏感字段泄漏出去的关键机制**，review 时要确认每个接口都声明了。

### 2.2 为什么没有 Repository 层

Spring Data JPA 里你写：

```java
public interface UserRepository extends JpaRepository<User, Long> {
    List<User> findByStatusAndDeptId(String status, Long deptId);
}
```

SQLAlchemy 里对应的东西长这样：

```python
# backend/app/services/user_service.py

def build_query(db, *, keyword=None, dept_id=None, status=None) -> Select:
    stmt = select(User)                                  # ← 相当于 SELECT u FROM User u
    if status:
        stmt = stmt.where(User.status == status)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(or_(User.username.like(like), User.real_name.like(like)))
    return stmt.order_by(User.id.desc())

# 调用处（api/v1/users.py）
stmt = user_service.build_query(db, keyword=keyword, dept_id=dept_id)
rows, total = paginate(db, stmt, paging)
```

**为什么没有 `UserRepository` 接口**：

- Python 没有编译期接口约束，写个「接口 + 实现」往往只是仪式感
- SQLAlchemy 的查询构造器（`select()`）本身就是 fluent API，`build_query` 返回的就是一条**未执行的查询**，
  可以继续 `.limit()` / `.offset()`，比 JPA 的 `Specification` 直观
- 业务逻辑集中在 `services/` 里，**查询构造是 service 的一部分**，不额外分一层

> **Review 提示**：想知道某个列表接口会发什么 SQL，找到 `build_query` 顺着看即可，
> 不用去猜 Spring Data 的方法名派生规则（这里没有那套魔法）。

### 2.3 Session = EntityManager，但有两个关键差异

```python
# backend/app/db/session.py
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,      # ← 差异 1
)

def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

SQLAlchemy 的 Session 也是 **Unit of Work**（像 Hibernate 的一级缓存 + 脏检查）：
`db.add(obj)` 只是把对象放进会话，**不是发 SQL**；真正的 UPDATE/INSERT 发生在你查询或 commit 时。

**差异 1：`expire_on_commit=False`**

Hibernate 默认 commit 后实体会变成 detached，访问属性会报 `LazyInitializationException`。
SQLAlchemy 默认（`expire_on_commit=True`）**类似**：commit 后所有属性被标记过期，
下次访问会**重新查库**。我们关掉了它，这样 `db.commit()` 之后还能直接读对象属性、
直接返回给 Pydantic 序列化，不用再查一次。

**代价**：commit 后的对象可能是**陈旧**的（比如数据库触发器等改了值）。所以本仓库里
需要拿到数据库最终值时，会显式 `db.refresh(obj)`，例如：

```python
db.commit()
db.refresh(user)      # 重新从库里读一遍
return user
```

**差异 2：没有 `@Transactional`，靠显式 commit**

这是最容易误判的地方。逐条对照：

| 场景 | Spring | 本仓库 |
|---|---|---|
| 事务开始 | 进 `@Transactional` 方法时自动 | 第一次执行 SQL 时**隐式**开始 |
| 事务提交 | 方法正常返回时自动 | **显式 `db.commit()`** |
| 异常回滚 | `@Transactional` 默认回滚 | 靠 `get_db` 的 `finally: db.close()` |
| 嵌套 | `REQUIRED`/`REQUIRES_NEW` 等传播行为 | **没有**，只有显式 commit |
| 只读事务 | `@Transactional(readOnly=true)` | 无对应物 |
| 事务边界在哪 | 注解声明的那个方法 | **`db.commit()` 那一行** |

**为什么异常还能回滚**？因为 `db.commit()` 没被执行，而 `get_db` 的 `finally` 会
`db.close()` —— 未提交的事务被丢弃。**效果上等价于回滚**，但请理解这是「没提交」
而不是「提交后回滚」。

> ⚠️ **Review 时必须盯的点**：如果某个 service 方法**中途 commit 了一次**，之后又抛异常，
> 那么第一次 commit 的改动**已经落库了**，不会回滚。这跟 Spring 里一个事务方法内部的
> 原子性保证不同。本仓库的做法是**一个公开的 service 方法 = 一次 commit**，
> 不要在中间插 commit。review 时看到两次 `db.commit()` 就要警觉。

**N+1 问题一样存在**。SQLAlchemy 默认 lazy loading，和 Hibernate 一样会在循环里发 N 条 SQL。
本仓库用 `lazy="selectin"` / `lazy="joined"` 显式声明预加载：

```python
# backend/app/models/org.py
role_links: Mapped[list[UserRole]] = relationship(
    "UserRole", back_populates="user", cascade="all, delete-orphan",
    lazy="selectin",       # ← 取 User 时顺带一条 SELECT 把所有 role_links 捞出来
)

# 而 UserRole.role 用 joined，避免取角色名时再来一轮 N+1
role: Mapped[Role] = relationship("Role", back_populates="user_links", lazy="joined")
```

> **Review 提示**：看到循环里访问 `obj.some_relationship`，先确认那个 relationship
> 是不是 lazy 的、外层查询有没有 `selectinload()`。

### 2.4 Pydantic = DTO + 校验，但它是**运行时**的

```python
# backend/app/schemas/org.py
class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=64, pattern=USERNAME_PATTERN)
    password: str = Field(min_length=6, max_length=72)
    real_name: str = Field(min_length=1, max_length=64)
    email: EmailStr | None = None
    role_ids: list[int] = Field(default_factory=list)      # ← 注意这里，见 §4.4
```

对应 Java：

```java
public record UserCreate(
    @NotBlank @Size(min=2, max=64) @Pattern(regexp = "...") String username,
    @Size(min=6, max=72) String password,
    @NotBlank String realName,
    @Email String email,
    List<Long> roleIds
) {}
```

**关键差异**：

| | Java Bean Validation | Pydantic v2 |
|---|---|---|
| 校验时机 | 框架触发 `@Valid` 时 | **构造对象时立即** |
| 底层实现 | 反射 + 注解处理器 | **Rust 核心**（pydantic-core），快得多 |
| 类型转换 | 不做 | **会做**（`"1"` → `1`，字符串转日期等） |
| 字段别名 / camelCase | `@JsonProperty` | `Field(alias=...)`（本项目**没用**，统一 snake_case） |
| 部分更新 | `@PatchMapping` + null 判断 | `model_fields_set`，见下 |

**`model_fields_set` 是 Python 这边的一个惯用法**，Java 没有直接对应物：

```python
class UserUpdate(BaseModel):
    real_name: str | None = None
    email: EmailStr | None = None
    dept_id: int | None = None

def update(db, user, payload: UserUpdate, ...):
    if payload.real_name is not None:          # ← 只判断值，无法区分「没传」和「传了 null」
        user.real_name = payload.real_name

    if "dept_id" in payload.model_fields_set:  # ← 能区分！「传了 dept_id=null」才进这里
        user.dept_id = payload.dept_id
```

**为什么必须区分**：`dept_id=null` 意思是「把用户移出部门」，而「不传 dept_id」意思是
「不改部门」。Java 里用 `Optional` + `@JsonInclude` 或专门的 PatchDTO，
Pydantic 用 `model_fields_set`（本次请求实际提供了哪些字段）。

> **Review 提示**：看到 `if xxx is not None` 和 `if "xxx" in payload.model_fields_set`
> 混用，要确认那个字段**是否允许被置空**。允许置空就必须用后者。

**错误响应形状**：Pydantic 校验失败时 FastAPI 抛 `RequestValidationError`，
本仓库在 `core/errors.py` 里统一改写成：

```json
{"detail": {"code": "VALIDATION_ERROR", "message": "参数校验未通过",
            "extra": {"errors": [{"field": "body.username", "message": "..."}]}}}
```

比 FastAPI 默认的嵌套 `loc` 数组好读，前端 `api/http.ts` 依赖这个形状。

### 2.5 同步 vs 异步 —— 一个必须知道的性能陷阱

FastAPI 支持两种路由函数：

```python
def sync_route(...):      # 普通函数 → 跑在 **线程池** 里
async def async_route(...):  # 协程 → 跑在 **事件循环** 里
```

**本仓库全部用同步 `def`**（见 §0 的决策 D2）。理由：同步 SQLAlchemy 会话
在千级用户规模下完全够用，省掉 async session 的学习与适配成本，且引擎单测更好写。

**陷阱**：如果你在 `async def` 路由里调用**同步阻塞**代码（比如同步 SQLAlchemy 查询），
会**阻塞整个事件循环**，所有并发请求一起卡住。这是 Java 工程师最容易忽略的点
—— Java 里阻塞一个线程池线程只影响那一个线程，Python 的 asyncio 是单线程事件循环。

> **Review 提示**：新增路由请**保持 `def`**。如果确实要写 `async def`，
> 里面的 IO 必须都是 await 的非阻塞调用（`httpx.AsyncClient` 之类），不能用同步 driver。

### 2.6 异常处理 = `@ControllerAdvice`

```python
# backend/app/core/errors.py
class AppError(Exception):
    status_code: int = 400
    code: str = "BAD_REQUEST"
    message: str = "请求有误"

class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"
    message = "资源不存在"

def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_payload())
```

service 里直接 `raise NotFoundError("用户不存在", code="USER_NOT_FOUND")`，
和 Spring 抛自定义异常 + `@ExceptionHandler` 是一个思路。

**约定**：所有错误响应体固定为
```json
{"detail": {"code": "...", "message": "...", "extra": {...}}}
```
`code` 是**给程序判断的**（前端按 `code` 分支），`message` 是**给人看的**，
`extra` 放结构化补充（如字段级错误列表）。

> **Review 提示**：service 层应该 `raise` 自定义异常，**不要** `raise HTTPException`
> —— 那会把 HTTP 概念泄漏到业务层，也和 Spring 里在 Service 抛 `ResponseStatusException` 一样是坏味道。

---

## 3. SQLAlchemy 2.0 详解

### 3.1 模型定义

```python
# backend/app/models/org.py
class User(Base, PkMixin, TimestampMixin):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    email: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dept_id: Mapped[int | None] = mapped_column(
        IntType, ForeignKey("departments.id"), nullable=True, index=True
    )

    department: Mapped[Department | None] = relationship(
        "Department", back_populates="users", foreign_keys="User.dept_id"
    )
```

对照 JPA：

| JPA | SQLAlchemy 2.0 |
|---|---|
| `@Entity` | 继承 `Base` |
| `@Table(name="users")` | `__tablename__ = "users"` |
| `@Id @GeneratedValue` | `PkMixin` 里的 `id: Mapped[int] = mapped_column(..., primary_key=True)` |
| `@Column(nullable=false)` | `mapped_column(String(64), nullable=False)` |
| `@Column` 类型 | **从 `Mapped[X]` 的注解推导**（`Mapped[str]` → `VARCHAR`） |
| `@OneToMany` / `@ManyToOne` | `relationship()` |
| `mappedBy` | `back_populates`（双向必须两边都写） |
| `@Enumerated(EnumType.STRING)` | 存 `String` + Python `StrEnum`（决策 D4） |
| `@MappedSuperclass` | **Mixin 类**（`PkMixin` / `TimestampMixin`） |

**三个容易看错的地方**：

1. **`Mapped[str | None]` 的 `| None` 决定 nullable**。虽然代码里也写了 `nullable=True`，
   但类型注解本身就是意图声明。看到 `Mapped[str]`（没有 `| None`）就是非空。

2. **`IntType` 是自定义的可移植类型**，不是标准 SQLAlchemy：
   ```python
   # backend/app/db/base.py
   IntType = BigInteger().with_variant(Integer, "sqlite")
   ```
   MySQL 上生成 `BIGINT`，SQLite 上生成 `INTEGER`（SQLite 只有 INTEGER 主键才能自增）。
   这是「先 SQLite 后 MySQL」需求的核心机制，**改动主键类型前务必理解它**。

3. **`default=` 是 Python 侧默认值，不是数据库 DDL 的 DEFAULT**。
   `default=False` 意味着「INSERT 时由 Python 填」，`server_default=` 才是 DDL 级别的。
   本仓库时间戳刻意用 Python 侧（见 §6 第 3 条陷阱）。

### 3.2 查询

```python
from sqlalchemy import select, func, or_

# 等价于 SELECT * FROM users WHERE status = 'ACTIVE' ORDER BY id DESC
stmt = select(User).where(User.status == "ACTIVE").order_by(User.id.desc())
users = db.scalars(stmt).all()          # .scalars() 取单列/单实体，.all() 执行

# 只取一列
name = db.scalar(select(Department.name).where(Department.id == 1))

# 单条
user = db.scalar(select(User).where(User.username == "admin"))
user = db.get(User, 1)                   # 按主键（走身份映射缓存，比 select 快）

# 计数
total = db.scalar(select(func.count()).select_from(stmt.subquery()))
```

**注意 `db.scalars()` vs `db.scalar()` vs `db.execute()`**：

| 方法 | 返回 | 用于 |
|---|---|---|
| `db.execute(stmt)` | `Result`（行元组） | 多列查询，`for row in result` 解包 |
| `db.scalars(stmt)` | `ScalarResult`（单值流） | `select(Entity)` 或 `select(单列)` |
| `db.scalar(stmt)` | 单个值或 `None` | 确定只返回一行一列 |
| `db.get(Entity, pk)` | 实体或 `None` | 按主键取（有缓存，不发 SQL 如果已加载） |

**`User.status == "ACTIVE"` 不是 Python 的比较** —— `==` 被 SQLAlchemy 重载成
「生成 SQL 的 `=` 条件」。这是 ORM 惯用手法（JPA Criteria API 的 Lambda 也是类似思路），
但在 Python 里没有编译器帮你区分「这是 SQL 表达式还是真在比较」。

> ⚠️ 这就是为什么 `if user.status == "ACTIVE":` 是**对**的，但
> `if User.status == "ACTIVE":` 在 `if` 里是**恒真**的（它返回一个 SQL 表达式对象，
> 而 Python 里非空对象恒为真）。Java 里 `if (field == "x")` 是编译错误，Python 不会报。

### 3.3 分页

```python
# backend/app/core/pagination.py
def paginate(db: Session, stmt: Select, params: PageParams) -> tuple[list, int]:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.scalars(stmt.limit(params.size).offset(params.offset)).all()
    return list(rows), total
```

`stmt.order_by(None)` 是清掉排序再套 `count(*)` —— 否则 `SELECT COUNT(*) ... ORDER BY x`
在某些数据库上会报错或白费排序。

---

## 4. Python 语言本身的坑（针对 Java / C# 背景）

这一节只讲**读本仓库代码时会遇到、且你的母语直觉会误导你**的点。

### 4.1 没有编译期类型检查

`mypy` / `ruff` 是可选的**静态检查工具**，不是编译器。Python 运行时**完全不看类型注解**：

```python
def create(db: Session, payload: UserCreate) -> User:
    ...

create("我不是 Session", "我不是 UserCreate")   # 运行时才可能报错，也可能不报
```

**对 review 的意义**：类型注解是**文档和工具提示**，不是保证。
判断一个函数会不会出错，要看**函数体**，不能只看签名。
（对照：Java 的泛型是编译期强制的，C# 的 `dynamic` 才不做检查。）

本仓库用 `ruff` 做 lint，但**没启用 mypy**。所以类型不匹配可能在运行时才暴露。

### 4.2 `from __future__ import annotations` —— 推迟求值，有真实副作用

很多文件开头有这一行：

```python
from __future__ import annotations
```

作用是：**把所有类型注解变成字符串，推迟到需要时才求值**。好处是能写前向引用
（`def f() -> User:` 时 `User` 还没定义也没关系）。

**但它会破坏依赖运行时反射的框架**。本仓库真实踩过：

```python
# backend/app/core/pagination.py —— 这个文件**故意**没有**那一行
"""...
注意：本模块不能加 `from __future__ import annotations`。
`PageParams.__init__` 的签名里用了 `Annotated[int, Query(...)]`，一旦注解被
推迟成字符串，FastAPI 就无法还原出它，会在请求处理时抛 PydanticUserError。
"""
```

> **Review 提示**：新增使用了 `Depends(...)` / `Query(...)` / `Annotated[...]` 的模块时，
> **不要**加 `from __future__ import annotations`。看到这类模块里有这一行，要怀疑。

### 4.3 缩进即语法

Java 用 `{}`，Python 用缩进。**制表符和空格混用会直接报 `TabError`**。
本仓库统一 4 空格（`.editorconfig` / ruff 保证）。

翻代码时注意：**一个块的范围就是缩进深度**，没有其他标记。
`if` / `for` / `def` 行尾的 `:` 是块开始。

### 4.4 可变默认参数 —— Python 最经典的坑

```python
def f(items: list[int] = []) -> None:   # ❌ 这个 [] 在**函数定义时**创建一次，
    items.append(1)                      #    所有调用共享同一个 list！
```

**正确写法**：

```python
class UserCreate(BaseModel):
    role_ids: list[int] = Field(default_factory=list)   # ✅ 每次调用新 list
```

```python
def get_role_codes(self, extra: list[str] | None = None) -> list[str]:
    extra = extra or []       # ✅ 或者用 None 作哨兵
```

对照 Java：Java 没有默认参数，所以没这个问题。C# 的默认参数值必须是编译期常量，
`new List<int>()` 也不允许。**Python 允许，所以这是个高频 bug 源。**

> **Review 提示**：搜索 `= []` / `= {}` / `= set()` 出现在函数签名里的地方，
> 以及 Pydantic 模型里 `list[...] = []`（应该是 `Field(default_factory=list)`）。

### 4.5 循环导入

Python 的 import 是**在模块顶层立即执行**的（不像 Java 的 import 只是声明）。
所以：

```python
# a.py
from b import something    # 执行到这一行时，b.py 会被完整执行

# b.py
from a import other        # 如果 a.py 还没执行完 → ImportError
```

**本仓库怎么避免的**：
- `core/policy.py` 用 `Protocol` 而不是导入 `models.User` —— 就是为了不让 `core` 依赖 `models`
- `models/org.py` 里的 relationship 用**字符串**而不是类：`relationship("Department", ...)`
- `from __future__ import annotations` 让类型注解不触发导入
- 函数体内 import（局部导入）作为最后手段

> **Review 提示**：`from app.models import X` 写在函数体里，通常是循环导入的权宜之计，
> 要问清是不是分层被破坏了。

### 4.6 真值判断：`if x:` 不等于 `if x is not None:`

Python 里这些值都是「假」：

```python
if not x:      # x 为 None / False / 0 / 0.0 / "" / [] / {} / set() 时都为真
```

**这会导致真实 bug**：

```python
if user.dept_id:              # ❌ dept_id = 0 时也是假（虽然 0 不是合法 id，但语义不对）
    do_something()

if user.dept_id is not None:  # ✅ 明确判断「有没有值」
    do_something()
```

本仓库里对可能为 `0` 或空字符串的值一律用 `is not None` / `is None` 判断。

另外 **`is` 比较的是对象身份（内存地址），`==` 比较的是值**：

```python
a is b        # 是不是同一个对象
a == b        # 值是否相等

x is None     # ✅ 惯用法
x == None     # ⚠️ 能工作但不推荐（除非重载了 __eq__）
```

对照 Java：`==` 对引用类型比地址，`equals()` 比值 —— Python 反过来，
`==` 默认比值，`is` 才比地址。

### 4.7 包管理与虚拟环境

| Java / C# | Python |
|---|---|
| `pom.xml` / `build.gradle` / `.csproj` | `requirements.txt`（本项目） |
| Maven 中央仓库 / NuGet | PyPI |
| `mvn dependency:tree` | `pip list` / `pip show <pkg>` |
| JDK 全局安装 | **虚拟环境 `.venv/`（每项目独立）** |
| `~/.m2/repository` 全局缓存 | venv 内独立安装 |

**虚拟环境是必须理解的**：`.venv/` 里有一份独立的 Python 解释器和依赖，
项目之间的包不共享。所以：

- **不能**直接 `python -m pytest`（那会用全局 Python，没有依赖）
- **要**用 `.venv/Scripts/python.exe -m pytest`（Windows）或先 `activate`
- 本仓库的 `scripts/*.sh` 已经替你处理了这件事

`requirements.txt` 里 `fastapi>=0.115,<0.121` 的语义和 Maven 的 `[0.115,0.121)` 一样，
但 **pip 默认不生成 lock 文件**，所以**同一个 requirements.txt 在不同时间安装可能得到不同版本**。
（前端 `package-lock.json` 是有的 —— npm 默认生成。）

> **Review 提示**：依赖上限（`<X`）是有意为之，别随手删。它挡的是破坏性升级。

---

## 5. Alembic = Flyway / EF Migrations

### 5.1 基本操作

```bash
bash scripts/migrate.sh                       # = alembic upgrade head
bash scripts/migrate.sh current               # 当前版本
bash scripts/migrate.sh history               # 历史
bash scripts/migrate.sh downgrade -1          # 回退一步
bash scripts/migrate.sh revision --autogenerate -m "描述"   # 按模型差异生成
```

对照：

| Flyway | Alembic |
|---|---|
| `V1__init.sql` | `alembic/versions/0001_m1_org_tables.py` |
| `flyway_schema_history` 表 | `alembic_version` 表 |
| `migrate` | `upgrade head` |
| `undo` | `downgrade` |
| 手写 SQL | **Python 代码**（`op.create_table(...)`） |

**和 Flyway 最大的不同**：Alembic 迁移是 **Python 脚本**，可以用循环、条件、
导入模型常量。`--autogenerate` 会对比「模型定义」和「数据库现状」自动生成脚本
—— 这和 **EF Core Migrations** 更像，Flyway/Liquibase 没有这个能力。

### 5.2 autogenerate 的三个坑

**坑 1：不识别重命名**。把 `user_name` 改成 `username`，autogenerate 会生成
「DROP COLUMN user_name + ADD COLUMN username」—— **数据全丢**。

> 生成后**必须打开文件核对**。看到无关的 drop/add 就是重命名被误判了，
> 手工改成 `op.alter_column("users", "user_name", new_column_name="username")`。

**坑 2：SQLite 不支持 ALTER**。SQLite 不能改列、删约束。所以 `env.py` 开了批处理模式：

```python
# backend/alembic/env.py
context.configure(
    connection=connection,
    target_metadata=target_metadata,
    render_as_batch=True,     # ← SQLite 上会「建新表→拷数据→换名」
    compare_type=True,
)
```

**坑 3：`alembic.ini` 必须保持纯 ASCII**。`alembic` 用 `encoding="locale"` 读它，
中文 Windows 上是 GBK，写 UTF-8 中文注释会在加载阶段直接
`UnicodeDecodeError`。这是本仓库唯一一个不写中文注释的配置文件（见 §6 第 1 条）。

### 5.3 为什么迁移是「按里程碑增量」的

PRD §6 列了 16 张表，但 `0001` 只建了 5 张（组织相关）。M2/M3 的迁移再建表单和流程表。

理由见决策 D3：引擎的数据结构在 M3 落地时仍可能微调，提前冻结 16 张表
等于把没验证的设计固化下来。**这是有意的，不是遗漏。**

---

## 6. 本仓库踩过的坑（照着这份清单能少走弯路）

这几条都是写这个项目时真实撞过的，review 时可以直接当检查项。

| # | 坑 | 症状 | 正确处理 |
|---|---|---|---|
| 1 | **`alembic.ini` 被用 GBK 读取** | UTF-8 中文注释导致 `UnicodeDecodeError` | 该文件保持纯 ASCII；其余文件 UTF-8 + 中文注释 |
| 2 | **pysqlite 不主动发 BEGIN** | 测试数据串场（分页 total 数字翻倍） | `conftest.py` 里设 `isolation_level=None` + 监听 `begin` 显式发 BEGIN |
| 3 | **时间戳不能用数据库默认值** | SQLite（UTC）与 MySQL（会话时区）差 8 小时 | 统一 naive UTC + 应用层生成（`core/clock.py`），前端补 `Z` 再转本地 |
| 4 | **`from __future__ import annotations` 破坏 FastAPI 反射** | 请求处理时抛 `PydanticUserError` | `core/pagination.py` 不写这一行 |
| 5 | **bcrypt 有 72 字节上限** | 超长密码在 bcrypt 4.x 抛 `ValueError`（登录变 500） | `security.py` 显式截断 + schema `max_length=72` |
| 6 | **`email-validator` 拒绝保留 TLD** | `admin@flowform.local` 校验失败返回 422 | 示例与种子统一用 `@example.com` |
| 7 | **ORM 对象直接序列化需 `from_attributes`** | `model_validate(orm_obj)` 抛 `model_type` 错误 | DTO 加 `model_config = ConfigDict(from_attributes=True)` |
| 8 | **Pydantic 可变默认值** | 多个实例共享同一个 list | `Field(default_factory=list)` |
| 9 | **antd 组件未注册不被任何构建关卡发现** | 页面渲染成空标签，但 typecheck / build 都通过 | 全局注册 + `src/__tests__/render.spec.ts` 渲染测试兜底 |

---

## 7. 调试手册

### 7.1 读 Python 的 traceback（和 Java 栈相反）

```
Traceback (most recent call last):        ← 注意这句：最近的在**最下面**
  File "app/api/v1/users.py", line 40, in create_user
    user = user_service.create(db, payload, actor=actor, ip=ip)
  File "app/services/user_service.py", line 62, in create
    raise ConflictError(f"用户名 {payload.username} 已存在", code="USERNAME_EXISTS")
ConflictError: 用户名 admin 已存在
```

**Java 是「Caused by」往下挖，最底层异常在最下；Python 是调用栈从外到内，
最底下那一行才是真正抛异常的位置。**

**关键技巧**：**从最下面往上读**——最后一行是异常类型 + 消息，
倒数第二段是抛出点，再往上才是调用链。

### 7.2 打断点

**方式一：代码里插 `breakpoint()`**（等价于 Java 的 IDE 断点 + C# 的 `Debugger.Break()`）

```python
def create(db, payload, ...):
    breakpoint()        # ← 执行到这里会停下，进入交互式调试器
    ...
```

运行到这时会掉进 `pdb`，常用命令：

| pdb 命令 | 作用 | Java/IDEA 对应 |
|---|---|---|
| `n` (next) | 单步跳过 | Step Over (F8) |
| `s` (step) | 单步进入 | Step Into (F7) |
| `r` (return) | 跑到当前函数返回 | Step Out (Shift+F8) |
| `c` (continue) | 继续运行 | Resume (F9) |
| `p expr` | 打印表达式 | Evaluate Expression |
| `pp expr` | 美化打印（长对象用这个） | |
| `l` (list) | 显示当前行周围代码 | |
| `w` (where) | 显示调用栈 | Stack Trace 面板 |
| `q` (quit) | 退出，程序终止 | |

**方式二：VS Code 断点**（推荐，有图形界面）

在 `.vscode/launch.json` 里加：

```jsonc
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "FlowForm 后端 (uvicorn)",
      "type": "debugpy",
      "request": "launch",
      "module": "uvicorn",
      "args": ["app.main:app", "--reload", "--host", "127.0.0.1", "--port", "8000"],
      "cwd": "${workspaceFolder}/backend",
      "python": "${workspaceFolder}/backend/.venv/Scripts/python.exe",
      "envFile": "${workspaceFolder}/backend/.env",
      "justMyCode": false          // ← 关掉，才能单步进 FastAPI/SQLAlchemy 内部
    },
    {
      "name": "pytest 当前文件",
      "type": "debugpy",
      "request": "launch",
      "module": "pytest",
      "args": ["-q", "${file}", "-x"],
      "cwd": "${workspaceFolder}/backend",
      "python": "${workspaceFolder}/backend/.venv/Scripts/python.exe",
      "justMyCode": false
    }
  ]
}
```

然后在编辑器左侧点行号打断点，按 F5 启动。

> **`justMyCode: false` 很重要**：默认 VS Code 只在你自己的代码里停，
> 但它会把「你的代码」判定为项目目录内的文件。关掉后可以单步进入
> FastAPI 的路由分发、Pydantic 的校验、SQLAlchemy 的 SQL 生成 —— 调试框架行为时必需。

### 7.3 看 SQL 实际发了什么

**最快的方式**：改 `backend/.env`

```
SQL_ECHO=true
```

重启后端，所有 SQL 会打到控制台（对应 Hibernate 的 `show_sql`）。

**更精细的方式**（代码里临时用）：

```python
stmt = user_service.build_query(db, ...)
print(stmt.compile(compile_kwargs={"literal_binds": True}))   # 打印带真实参数的 SQL
```

**方式三：在测试里断言 SQL**（review 时验证 N+1 的利器）：

```python
from sqlalchemy import event

def test_no_n_plus_1(db):
    statements = []
    event.listen(db.bind, "before_cursor_execute",
                 lambda conn, cur, stmt, *a: statements.append(stmt))
    user_service.to_out_many(db, users)
    assert len(statements) <= 2      # 期望只发 1~2 条，不是 N 条
```

### 7.4 常用诊断命令

```bash
cd backend && source .venv/Scripts/activate     # Git Bash

# 交互式 shell，直接查库（相当于 Spring Boot 的 h2-console / JHipster 的 shell）
python -c "
from app.db.session import SessionLocal
from app.models import User
from sqlalchemy import select
with SessionLocal() as db:
    for u in db.scalars(select(User)).all():
        print(u.id, u.username, u.real_name, u.role_codes)
"

# 看某个接口注册了没、依赖了什么
python -c "
from app.main import app
for r in app.routes:
    if hasattr(r, 'methods') and '/users' in str(r.path):
        print(sorted(r.methods), r.path, '->', r.name)
"

# 看 A 接口实际会生成什么 SQL
python -c "
from sqlalchemy import select
from app.models import User
from app.services import user_service
from app.db.session import SessionLocal
with SessionLocal() as db:
    print(user_service.build_query(db, keyword='admin').compile())
"

# 校验迁移和模型是否一致（不会改库，只报告差异）
alembic check
```

### 7.5 日志

```python
# 任何模块里
import logging
logger = logging.getLogger(__name__)     # ← 用 __name__，日志里会显示模块路径
logger.info("处理用户 %s", user.id)       # ← 用 %s 占位，不要 f-string（见下）
logger.warning("...")
logger.exception("...")                   # ← 在 except 块里用，会自动带上 traceback
```

对应 SLF4J 的 `LoggerFactory.getLogger(X.class)`。日志级别在 `app/main.py` 配置。

> **为什么不用 f-string 拼日志**：`logger.info(f"...{obj}")` 无论级别是否开启都会
> **先执行**字符串拼接（可能触发昂贵的 `__repr__` / 懒加载查询）。
> `logger.info("%s", obj)` 由 logging 在确定要输出时才格式化。

---

## 8. Review 检查清单

拿这份清单过一遍 PR，能覆盖 Python 这边最容易出的问题。

### 8.1 分层与结构

- [ ] `api/` 只做参数解析、权限、调用 service、返回 —— **没有业务逻辑**
- [ ] `services/` 里**没有** `Request` / `HTTPException` / 状态码
- [ ] `models/` **没有**导入 `services` / `api`（会导致循环导入）
- [ ] `core/` 没有导入 `models`（`policy.py` 用 Protocol 就是为了守这条）
- [ ] 新增接口声明了 `response_model`（否则可能把 `password_hash` 吐出去）

### 8.2 事务与并发

- [ ] 一个公开的 service 方法**只有一次 `db.commit()`**
- [ ] commit 之后要读数据库最终值的，有 `db.refresh(obj)`
- [ ] 需要区分「没传字段」和「传了 null」的地方用了 `model_fields_set`
- [ ] 循环里访问 relationship 的地方，确认没有 N+1

### 8.3 Python 特有陷阱

- [ ] 函数签名里没有可变默认参数（`= []` / `= {}`）
- [ ] Pydantic 里 list/dict 字段用 `Field(default_factory=...)`
- [ ] 使用了 `Depends` / `Query` / `Annotated` 的模块**没有** `from __future__ import annotations`
- [ ] 可能为 `0` / `""` 的值用 `is None` / `is not None` 判断，不用 `if x:`
- [ ] 新路由是同步 `def`（除非确知要异步 IO）

### 8.4 数据库

- [ ] 迁移文件**人工核对过**，没有把重命名误判成 drop+add
- [ ] 新列类型是方言无关的（不写 MySQL/SQLite 专有 DDL）
- [ ] 时间字段用 `default=utcnow` 而不是 `server_default=func.now()`
- [ ] 新表的主键用 `IntType`（`db/base.py` 里的可移植类型）

### 8.5 测试

- [ ] 新增错误路径有对应测试（不只测 happy path）
- [ ] 新增前端页面补进了 `src/__tests__/render.spec.ts` 的 `MOUNTED_VIEWS`

---

## 9. 附录：命令对照

| 做什么 | Spring / .NET | 本仓库 |
|---|---|---|
| 装依赖 | `mvn install` / `dotnet restore` | `pip install -r requirements.txt` |
| 启动 | `mvn spring-boot:run` / `dotnet run` | `bash scripts/dev-backend.sh` |
| 跑测试 | `mvn test` / `dotnet test` | `bash scripts/check.sh` 或 `pytest -q` |
| 单个测试 | `-Dtest=XxxTest` / `--filter` | `pytest tests/test_users.py::test_create -q` |
| 数据库迁移 | `flyway migrate` / `dotnet ef database update` | `bash scripts/migrate.sh` |
| 生成迁移 | 手写 / `dotnet ef migrations add` | `bash scripts/migrate.sh revision --autogenerate -m "..."` |
| 看依赖树 | `mvn dependency:tree` | `pip list` |
| 格式化 | `spotless:apply` / `dotnet format` | `ruff format app tests` |
| 静态检查 | `mvn checkstyle:check` | `ruff check app tests` |
| Lint 自动修 | — | `ruff check --fix app tests` |

---

## 10. 延伸阅读

- `docs/TECH-DESIGN.md` §9「已知陷阱」—— 项目层面的坑，和本文 §6 互补
- `backend/app/core/pagination.py` 文件头 —— `from __future__` 陷阱的现场说明
- `backend/alembic/env.py` 文件头 —— 为什么 `render_as_batch=True`
- `backend/app/db/base.py` —— 可移植类型 `IntType` 的定义与理由
- 官方文档：[FastAPI](https://fastapi.tiangolo.com/) ·
  [SQLAlchemy 2.0 ORM](https://docs.sqlalchemy.org/en/20/orm/) ·
  [Alembic](https://alembic.sqlalchemy.org/) ·
  [Pydantic v2](https://docs.pydantic.dev/)
