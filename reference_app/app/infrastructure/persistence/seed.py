from __future__ import annotations

from typing import Any

from sqlalchemy import select

from ...application.auth.ports import PasswordHasherPort
from .models.catalog import (
    JobDomain,
    JobRole,
    QuestionBank,
    StarGuidanceTemplate,
    QuestionSet,
    QuestionSetItem,
)
from .models.enums import ExperienceLevel, Language, QuestionType, UserRole, UserStatus
from .models.user import User


def seed_default_data(session_factory: Any, hasher: PasswordHasherPort) -> None:
    session = session_factory()
    try:
        # 1. Seed Default Admin if not present
        existing_admin = session.execute(
            select(User).where(User.email == "admin@interviewly.io")
        ).scalar_one_or_none()
        if existing_admin is None:
            admin_user = User(
                full_name="System Administrator",
                email="admin@interviewly.io",
                password_hash=hasher.hash("Admin@123456"),
                phone="0900000000",
                role=UserRole.admin,
                status=UserStatus.active,
                preferred_language=Language.vi,
            )
            session.add(admin_user)
            session.commit()

        # 2. Check if domains already exist
        has_domain = session.execute(select(JobDomain)).first()
        if has_domain is not None:
            seed_rich_questions_and_sets(session)
            return

        # 3. Seed Standard Domains
        it_domain = JobDomain(
            domain_name="Công nghệ thông tin (IT)",
            description="Phát triển phần mềm, hạ tầng điện toán đám mây, dữ liệu và an toàn thông tin.",
        )
        marketing_domain = JobDomain(
            domain_name="Marketing & Truyền thông",
            description="Digital Marketing, sáng tạo nội dung, SEO/SEM và xây dựng thương hiệu.",
        )
        sales_domain = JobDomain(
            domain_name="Kinh doanh & Phát triển thị trường",
            description="Bán hàng B2B, quản trị quan hệ khách hàng và tư vấn giải pháp.",
        )
        hr_domain = JobDomain(
            domain_name="Quản trị Nhân sự (HR)",
            description="Tuyển dụng nhân tài, xây dựng văn hóa doanh nghiệp và chế độ đãi ngộ.",
        )
        finance_domain = JobDomain(
            domain_name="Tài chính & Kế toán",
            description="Phân tích tài chính doanh nghiệp, kế toán quản trị và kiểm toán.",
        )
        session.add_all([it_domain, marketing_domain, sales_domain, hr_domain, finance_domain])
        session.commit()

        # 4. Seed Standard Roles
        roles = [
            JobRole(domain_id=it_domain.domain_id, role_name="Backend Engineer", description="Xây dựng API, kiến trúc cơ sở dữ liệu và xử lý nghiệp vụ phía máy chủ."),
            JobRole(domain_id=it_domain.domain_id, role_name="Frontend Engineer", description="Phát triển giao diện web người dùng với React, Next.js, Vue."),
            JobRole(domain_id=it_domain.domain_id, role_name="Fullstack Developer", description="Phát triển toàn diện ứng dụng từ giao diện người dùng đến dịch vụ backend."),
            JobRole(domain_id=it_domain.domain_id, role_name="DevOps / SRE Engineer", description="Tự động hóa CI/CD, giám sát hạ tầng cloud AWS/GCP và container Kubernetes."),
            JobRole(domain_id=it_domain.domain_id, role_name="Data / AI Engineer", description="Xử lý pipeline dữ liệu lớn, triển khai mô hình Machine Learning và tích hợp AI."),
            JobRole(domain_id=marketing_domain.domain_id, role_name="Digital Marketing Specialist", description="Chạy chiến dịch quảng cáo đa kênh Facebook Ads, Google Ads và TikTok."),
            JobRole(domain_id=marketing_domain.domain_id, role_name="Content & SEO Creator", description="Sản xuất nội dung bài viết, kịch bản video và tối ưu hóa thứ hạng tìm kiếm."),
            JobRole(domain_id=sales_domain.domain_id, role_name="B2B Account Executive", description="Tìm kiếm khách hàng doanh nghiệp, đàm phán hợp đồng thương mại."),
            JobRole(domain_id=hr_domain.domain_id, role_name="Talent Acquisition (Recruiter)", description="Tìm nguồn, phỏng vấn sàng lọc và thu hút ứng viên chất lượng cao."),
            JobRole(domain_id=finance_domain.domain_id, role_name="Financial Analyst", description="Phân tích báo cáo tài chính, dự báo dòng tiền và đánh giá dự án đầu tư."),
        ]
        session.add_all(roles)
        session.commit()

        # 5. Seed STAR Guidance Templates
        star_general = StarGuidanceTemplate(
            title="Mẫu STAR Phỏng vấn Hành vi Chuẩn",
            situation_guide="Mô tả ngắn gọn bối cảnh dự án hoặc tình huống cụ thể (ở đâu, khi nào, ai tham gia).",
            task_guide="Nêu rõ mục tiêu hoặc thử thách cụ thể bạn phải giải quyết trong tình huống đó.",
            action_guide="Trình bày chi tiết các bước bạn trực tiếp thực hiện (suy nghĩ, công cụ, kỹ năng sử dụng).",
            result_guide="Nêu kết quả định lượng cụ thể đạt được (tăng % hiệu năng, giảm thời gian, bài học kinh nghiệm rút ra).",
            language=Language.vi,
        )
        star_tech = StarGuidanceTemplate(
            title="Mẫu STAR Giải quyết Sự cố Kỹ thuật (Technical Incident)",
            situation_guide="Hệ thống gặp lỗi gì, ảnh hưởng đến bao nhiêu người dùng, phát hiện lúc nào.",
            task_guide="Mục tiêu khắc phục sự cố, phục hồi dữ liệu hoặc giảm thiểu thiệt hại.",
            action_guide="Cách bạn debug, tra cứu log, đưa ra phương án vá lỗi tạm thời và giải pháp triệt để.",
            result_guide="Hệ thống hoạt động bình thường trở lại sau bao lâu, biện pháp phòng ngừa tương lai.",
            language=Language.vi,
        )
        star_en = StarGuidanceTemplate(
            title="Standard STAR Behavioral Framework",
            situation_guide="Briefly describe the context, challenge or project background.",
            task_guide="Explain what was required of you and your specific role or goal.",
            action_guide="Detail the actions you took personally to address the challenge.",
            result_guide="Share the measurable outcomes and key learnings from your actions.",
            language=Language.en,
        )
        session.add_all([star_general, star_tech, star_en])
        session.commit()

        # 6. Seed Sample Questions
        backend_role = next(r for r in roles if r.role_name == "Backend Engineer")
        frontend_role = next(r for r in roles if r.role_name == "Frontend Engineer")
        devops_role = next(r for r in roles if r.role_name == "DevOps / SRE Engineer")

        questions = [
            QuestionBank(
                domain_id=it_domain.domain_id,
                role_id=backend_role.role_id,
                experience_level=ExperienceLevel.junior,
                language=Language.vi,
                question_type=QuestionType.behavioral,
                question_text="Hãy kể về một lần bạn gặp phải một bug khó trên môi trường production và cách bạn xử lý nó?",
                star_template_id=star_tech.star_template_id,
                is_active=True,
            ),
            QuestionBank(
                domain_id=it_domain.domain_id,
                role_id=backend_role.role_id,
                experience_level=ExperienceLevel.mid,
                language=Language.vi,
                question_type=QuestionType.technical,
                question_text="Bạn tối ưu hóa hiệu năng truy vấn cơ sở dữ liệu bị chậm (slow query) trong hệ thống như thế nào?",
                star_template_id=star_tech.star_template_id,
                is_active=True,
            ),
            QuestionBank(
                domain_id=it_domain.domain_id,
                role_id=frontend_role.role_id,
                experience_level=ExperienceLevel.junior,
                language=Language.vi,
                question_type=QuestionType.behavioral,
                question_text="Kể về một tình huống bạn có bất đồng quan điểm về thiết kế UI/UX với đồng nghiệp hoặc Product Manager và cách giải quyết?",
                star_template_id=star_general.star_template_id,
                is_active=True,
            ),
            QuestionBank(
                domain_id=it_domain.domain_id,
                role_id=backend_role.role_id,
                experience_level=ExperienceLevel.junior,
                language=Language.en,
                question_type=QuestionType.behavioral,
                question_text="Tell me about a challenging project deadline you faced and how you prioritized your engineering tasks?",
                star_template_id=star_en.star_template_id,
                is_active=True,
            ),
            QuestionBank(
                domain_id=it_domain.domain_id,
                role_id=devops_role.role_id,
                experience_level=ExperienceLevel.mid,
                language=Language.vi,
                question_type=QuestionType.situational,
                question_text="Nếu pipeline CI/CD bất ngờ bị nghẽn trong đợt release gấp của toàn đội ngũ, bạn sẽ ưu tiên xử lý các bước nào trước?",
                star_template_id=star_tech.star_template_id,
                is_active=True,
            ),
        ]
        session.add_all(questions)
        session.commit()
        seed_rich_questions_and_sets(session)
    finally:
        session.close()


def seed_rich_questions_and_sets(session: Any) -> None:
    """
    Seeds comprehensive real questions with contextual quiz scenarios,
    STAR benchmark sample answers, and curated question sets in PostgreSQL.
    """
    from decimal import Decimal

    # Find existing questions
    questions = list(session.execute(select(QuestionBank).order_by(QuestionBank.question_id)).scalars().all())
    if not questions:
        return

    # Question 1: Critical Bug Production
    q1 = questions[0]
    q1.question_text = "Hãy kể về một lần bạn gặp phải một critical bug trên production và cách bạn xử lý nó?"
    q1.quiz_data = {
        "question": "Khi phát hiện một critical bug làm tăng đột biến tỉ lệ lỗi giao dịch trên Production, bước xử lý ban đầu nào thể hiện tư duy kỹ thuật chuẩn xác nhất?",
        "options": [
            {
                "id": "A",
                "text": "Vội vàng sửa code trực tiếp trên production server để dập lỗi nhanh nhất có thể.",
                "is_correct": False,
                "explanation": "Sửa trực tiếp trên production vi phạm nghiêm trọng quy trình release, không thể rollback và dễ tạo ra cascade failures.",
            },
            {
                "id": "B",
                "text": "Áp dụng quy trình incident: Bật circuit breaker/chuyển bớt traffic, kiểm tra log trace nguyên nhân, viết hotfix và kiểm thử trước khi release.",
                "is_correct": True,
                "explanation": "Cách tiếp cận chuẩn mực: cô lập sự cố, bảo vệ người dùng, trace nguyên nhân gốc rễ và release hotfix an toàn qua quy trình.",
            },
            {
                "id": "C",
                "text": "Đổ lỗi cho bộ phận QA không bắt được lỗi ở môi trường Staging.",
                "is_correct": False,
                "explanation": "Tư duy tiêu cực, làm mất tinh thần đồng đội và không tập trung vào việc phục hồi hệ thống.",
            },
            {
                "id": "D",
                "text": "Tắt toàn bộ dịch vụ và chờ đến sáng thứ Hai giải quyết.",
                "is_correct": False,
                "explanation": "Gây gián đoạn kinh doanh nghiêm trọng và vi phạm SLA cam kết với khách hàng.",
            },
        ],
        "explanation": "Xử lý sự cố production đòi hỏi sự bình tĩnh, cô lập rủi ro, phân tích logs/APM và release hotfix theo quy trình an toàn.",
    }
    q1.sample_answer = "Trong một đợt phát hành tính năng thanh toán vào tối thứ Sáu, hệ thống ghi nhận tỉ lệ giao dịch thất bại tăng đột biến lên 28% do lỗi connection pool bị cạn kiệt. Sau khi nhận cảnh báo từ Prometheus, tôi đã lập tức thông báo trên kênh incident, chuyển bớt traffic sang replica và nhanh chóng trace log bằng Sentry. Tôi phát hiện một truy vấn ORM không giải phóng connection khi xảy ra timeout. Tôi đã viết hotfix điều chỉnh connection timeout và bổ sung khối try-finally giải phóng tài nguyên. Trong vòng 25 phút, tỉ lệ lỗi trở về 0%. Sau sự cố, tôi tổ chức post-mortem và bổ sung bài test stress-test 500 connection concurrent vào CI/CD pipeline."
    q1.follow_up_questions = [
        "Tại sao bài kiểm thử ở môi trường Staging trước đó không bắt được lỗi cạn kiệt connection này?",
        "Nếu sự cố xảy ra ngay thời điểm Black Friday với lượng truy cập gấp 10 lần, bạn sẽ áp dụng chiến lược degrade tính năng nào?",
    ]
    q1.tips = [
        "Nhấn mạnh tinh thần bình tĩnh, tuân thủ quy trình xử lý sự cố thay vì vội vàng đẩy code chưa kiểm tra.",
        "Luôn đưa ra con số định lượng (thời gian phát hiện, thời gian khắc phục, tỉ lệ lỗi giảm).",
    ]

    # Question 2: Database Slow Query
    if len(questions) > 1:
        q2 = questions[1]
        q2.question_text = "Bạn tiếp cận và tối ưu hóa một câu lệnh truy vấn cơ sở dữ liệu bị chậm (slow query) đang làm nghẽn API như thế nào?"
        q2.quiz_data = {
            "question": "Khi tối ưu câu lệnh SQL query bị chậm trên bảng có hơn 10 triệu bản ghi, hành động đầu tiên bạn nên làm là gì?",
            "options": [
                {
                    "id": "A",
                    "text": "Tăng RAM và CPU cho database server ngay lập tức.",
                    "is_correct": False,
                    "explanation": "Tăng phần cứng (vertical scaling) tốn kém chi phí và chỉ che đậy vấn đề chứ không giải quyết nguyên nhân gốc rễ.",
                },
                {
                    "id": "B",
                    "text": "Dùng EXPLAIN ANALYZE để kiểm tra Execution Plan, xem có Sequential Scan và thiếu Index ở các cột điều kiện/join hay không.",
                    "is_correct": True,
                    "explanation": "Hành động chuẩn mực: profiling và phân tích kế hoạch thực thi trước khi quyết định đánh index hoặc viết lại câu lệnh.",
                },
                {
                    "id": "C",
                    "text": "Xóa bớt dữ liệu cũ trên bảng để bảng nhẹ hơn.",
                    "is_correct": False,
                    "explanation": "Xóa dữ liệu làm mất dữ liệu lịch sử của người dùng nếu chưa có chiến lược lưu trữ archival.",
                },
                {
                    "id": "D",
                    "text": "Bỏ ORM và chuyển sang viết raw SQL không cần kiểm tra index.",
                    "is_correct": False,
                    "explanation": "Raw SQL nếu không đánh index vẫn quét toàn bảng (Seq Scan) gây nghẽn đĩa như thường.",
                },
            ],
            "explanation": "Luôn bắt đầu bằng công cụ profiling (EXPLAIN ANALYZE) để biết database tốn thời gian ở đâu trước khi tối ưu.",
        }
        q2.sample_answer = "Khi API lịch sử giao dịch tăng thời gian phản hồi lên 3.2 giây vào giờ cao điểm, tôi sử dụng lệnh EXPLAIN ANALYZE của PostgreSQL để kiểm tra kế hoạch thực thi. Tôi nhận thấy database đang thực hiện Sequential Scan trên bảng có hơn 12 triệu bản ghi vì thiếu composite index cho cặp cột (user_id, created_at). Tôi đã tạo một B-Tree composite index với cờ CONCURRENTLY để không lock bảng, đồng thời điều chỉnh lại truy vấn dùng keyset pagination thay thế cho OFFSET lớn. Kết quả là thời gian thực thi câu lệnh giảm từ 3200ms xuống còn 42ms, CPU database server giảm từ 85% xuống 25%."
        q2.follow_up_questions = [
            "Khi nào việc đánh thêm index lại gây hại nhiều hơn có lợi cho cơ sở dữ liệu?",
            "Làm thế nào để bạn lưu cache (Redis caching) cho truy vấn này mà không gặp phải vấn đề Cache Invalidation hoặc Cache Stampede?",
        ]
        q2.tips = [
            "Bắt đầu bằng phương pháp đo lường (profiling) trước khi đi thẳng vào giải pháp.",
            "Giải thích rõ ràng cơ chế index hoạt động dưới tầng đĩa và bộ nhớ.",
        ]

    # Question 3: Conflict Resolution & UI Discussion
    if len(questions) > 2:
        q3 = questions[2]
        q3.question_text = "Kể về một tình huống bạn có bất đồng quan điểm về thiết kế UI/UX hoặc giải pháp kỹ thuật với đồng nghiệp và cách giải quyết?"
        q3.quiz_data = {
            "question": "Khi có bất đồng ý kiến về kiến trúc kỹ thuật với đồng nghiệp trong cuộc họp Sprint, thái độ và hành động nào thể hiện tính chuyên nghiệp cao nhất?",
            "options": [
                {
                    "id": "A",
                    "text": "Giữ im lặng và sau đó làm theo ý mình khi viết code.",
                    "is_correct": False,
                    "explanation": "Làm việc đơn độc, thiếu minh bạch và gây rủi ro conflict lớn cho toàn đội.",
                },
                {
                    "id": "B",
                    "text": "Chủ động đề xuất thảo luận 20 phút, chuẩn bị dữ liệu đo lường/benchmark hoặc prototype trực quan để trao đổi khách quan.",
                    "is_correct": True,
                    "explanation": "Giải quyết bất đồng dựa trên dữ liệu khách quan (data-driven) và đặt lợi ích sản phẩm lên hàng đầu.",
                },
                {
                    "id": "C",
                    "text": "Tranh cãi gay gắt để bảo vệ quan điểm đến cùng bất kể thời gian.",
                    "is_correct": False,
                    "explanation": "Gây rạn nứt quan hệ đồng nghiệp và làm chậm tiến độ sprint.",
                },
                {
                    "id": "D",
                    "text": "Báo cáo ngay lên cấp trên để nhờ can thiệp xử ép đồng nghiệp.",
                    "is_correct": False,
                    "explanation": "Thiếu kỹ năng giao tiếp 1-1 và khả năng thương lượng trực tiếp.",
                },
            ],
            "explanation": "Thuyết phục bằng dữ liệu thực tế (Analytics, prototype, benchmarks) thay vì áp đặt cái tôi cá nhân.",
        }
        q3.sample_answer = "Khi Product Manager yêu cầu thêm một bảng dữ liệu động với hơn 30 cột vào màn hình di động, tôi nhận thấy giao diện này sẽ gây trải nghiệm cực kỳ ức chế cho người dùng. Tôi đã hẹn PM và Designer một buổi thảo luận 20 phút. Tôi chuẩn bị sẵn số liệu Google Analytics cho thấy 72% người dùng truy cập bằng smartphone, cùng với 1 bản prototype dạng thẻ thu gọn thông tin quan trọng kèm nút xem chi tiết. Cả đội ngũ đã đồng thuận với phương án của tôi, giúp tính năng phát hành đúng hạn với chỉ số hài lòng đạt 4.8/5 sao từ khảo sát người dùng."
        q3.follow_up_questions = [
            "Nếu PM vẫn kiên quyết yêu cầu làm theo cách cũ dù số liệu chỉ ra bất lợi, bạn sẽ phản hồi ra sao?",
            "Bạn cân bằng giữa tốc độ ship tính năng của công ty khởi nghiệp và chất lượng code bền vững như thế nào?",
        ]
        q3.tips = [
            "Thể hiện tư duy đặt lợi ích của người dùng và sản phẩm lên trên cái tôi cá nhân.",
            "Sử dụng dữ liệu thực tế và nguyên mẫu trực quan làm công cụ thuyết phục.",
        ]

    # Question 4: Web Vitals & Next.js Performance
    if len(questions) > 3:
        q4 = questions[3]
        q4.question_text = "Làm thế nào để bạn cải thiện điểm số Core Web Vitals (LCP, CLS, INP) cho một ứng dụng Next.js có kích thước lớn?"
        q4.quiz_data = {
            "question": "Để cải thiện chỉ số LCP (Largest Contentful Paint) bị chậm trên trang chủ Next.js do hình ảnh hero banner lớn, giải pháp nào là tối ưu nhất?",
            "options": [
                {
                    "id": "A",
                    "text": "Xóa toàn bộ hình ảnh và chỉ hiển thị văn bản thuần.",
                    "is_correct": False,
                    "explanation": "Làm suy giảm nghiêm trọng trải nghiệm thị giác và tỷ lệ chuyển đổi của website.",
                },
                {
                    "id": "B",
                    "text": "Sử dụng next/image với priority={true}, fetchpriority='high', chuyển định dạng sang WebP/AVIF và nén kích thước phù hợp với viewport.",
                    "is_correct": True,
                    "explanation": "Chuẩn tối ưu Core Web Vitals: ưu tiên tải sớm tài nguyên LCP bằng HTTP priority và định dạng nén hiện đại.",
                },
                {
                    "id": "C",
                    "text": "Chuyển ảnh sang dạng Base64 nhúng thẳng vào file HTML.",
                    "is_correct": False,
                    "explanation": "Nhúng Base64 làm phình to kích thước HTML document, làm chậm TTFB và render-blocking.",
                },
                {
                    "id": "D",
                    "text": "Dùng JavaScript tải ảnh sau khi trang đã load xong hoàn toàn.",
                    "is_correct": False,
                    "explanation": "Trì hoãn tải ảnh hero banner sẽ làm chỉ số LCP càng tăng cao hơn nữa.",
                },
            ],
            "explanation": "Sử dụng next/image với priority và format hiện đại là chuẩn mực tối ưu LCP trong hệ sinh thái Next.js.",
        }
        q4.sample_answer = "Tại trang chủ của hệ thống thương mại điện tử, điểm LCP ban đầu là 4.6s và CLS là 0.28 do tải quá nhiều hình ảnh chưa nén và font chữ gây layout shift. Tôi tiến hành phân tích bằng Chrome Lighthouse và bundle-analyzer. Đầu tiên, tôi chuyển đổi các component nặng phía dưới màn hình đầu tiên sang dynamic import với React.lazy. Thứ hai, tôi cấu hình next/image tự động chuyển đổi sang WebP/AVIF và bổ sung thuộc tính fetchpriority='high' cho banner chính. Thứ ba, áp dụng font-display: optional để dứt điểm layout shift. Điểm LCP giảm xuống còn 1.8s, CLS về 0.02 và điểm hiệu năng tổng thể tăng từ 51 lên 94 điểm."
        q4.follow_up_questions = [
            "Chỉ số INP (Interaction to Next Paint) đo lường điều gì và cách tối ưu các tác vụ JavaScript dài?",
            "Bạn phân chia chiến lược render Server-Side (SSR), Static (SSG) hay Client-Side (CSR) như thế nào cho từng trang?",
        ]
        q4.tips = [
            "Nắm vững định nghĩa các chỉ số Core Web Vitals của Google.",
            "Kể tên các công cụ đo lường thực tế bạn đã áp dụng.",
        ]

    # Question 5: CI/CD Pipeline Incident
    if len(questions) > 4:
        q5 = questions[4]
        q5.question_text = "Nếu một đường ống CI/CD bị nghẽn đúng vào thời điểm toàn công ty cần triển khai bản sửa lỗi khẩn cấp, bạn sẽ xử lý tình huống này theo thứ tự ưu tiên nào?"
        q5.quiz_data = {
            "question": "Khi hệ thống CI/CD runner bị nghẽn disk space đúng lúc cần release hotfix gấp cho toàn công ty, bước hành động khẩn cấp đầu tiên của bạn là gì?",
            "options": [
                {
                    "id": "A",
                    "text": "Dừng toàn bộ dự án và đợi hôm sau mua ổ cứng mới về gắn.",
                    "is_correct": False,
                    "explanation": "Gây tê liệt hoạt động của toàn bộ doanh nghiệp.",
                },
                {
                    "id": "B",
                    "text": "Kích hoạt ngay runner dự phòng có sẵn cache trên cloud để hotfix pipeline chạy ngay trong 10 phút, đồng thời dọn dẹp dangling images trên cụm chính.",
                    "is_correct": True,
                    "explanation": "Phân tách rõ ràng giữa giải pháp dập lửa tức thì (short-term failover) và giải pháp khắc phục triệt để (long-term cleanup).",
                },
                {
                    "id": "C",
                    "text": "Tắt toàn bộ các bài unit test và deploy thẳng code thô lên production không qua pipeline.",
                    "is_correct": False,
                    "explanation": "Rủi ro cực cao, có thể gây sập toàn bộ hệ thống vì code chưa được kiểm chứng.",
                },
                {
                    "id": "D",
                    "text": "Xóa toàn bộ cơ sở dữ liệu git repository trên server.",
                    "is_correct": False,
                    "explanation": "Hành động phá hoại làm mất mát mã nguồn.",
                },
            ],
            "explanation": "Trong sự cố DevOps, luôn ưu tiên giải pháp failover dự phòng tức thì trước khi xử lý tận gốc vấn đề.",
        }
        q5.sample_answer = "Khi đường ống CI/CD GitLab runner bị treo do hết disk space trên cụm build nodes trong giờ cao điểm release, tôi chia việc xử lý làm 2 giai đoạn: Khẩn cấp và Triệt để. Ở giai đoạn khẩn cấp, tôi kích hoạt một runner dự phòng trên AWS EC2 với docker cache có sẵn để các đội nhóm có thể chạy pipeline hotfix trong vòng 10 phút. Song song đó, tôi dọn dẹp các dangling docker images và volume cũ trên cụm runner chính. Về lâu dài, tôi viết daemon script tự động prune định kỳ khi ổ cứng vượt ngưỡng 80%, đồng thời thiết lập cảnh báo Prometheus khi disk space runner đạt 75%."
        q5.follow_up_questions = [
            "Làm sao để đảm bảo an toàn bí mật (secrets/API keys) khi chạy pipeline trên các runner linh hoạt?",
            "Bạn triển khai chiến lược Canary deployment hay Blue/Green deployment để giảm thiểu rủi ro khi release?",
        ]
        q5.tips = [
            "Phân biệt rõ ràng giữa giải pháp dập lửa tức thì và giải pháp ngăn ngừa tái phát.",
        ]

    # Seed 3 Real Curated Question Sets in DB if not existing
    existing_sets = list(session.execute(select(QuestionSet)).scalars().all())
    if not existing_sets:
        set1 = QuestionSet(
            title="Bộ đề phỏng vấn Full Stack Java - Fresher (Spring Boot & PostgreSQL)",
            description="Khung đề thi phỏng vấn tiêu chuẩn dành cho sinh viên mới ra trường và fresher: Kiểm tra kiến thức OOP, Spring Boot IoC/DI, Hibernate N+1, tối ưu câu lệnh SQL và giải quyết bug.",
            domain_id=q1.domain_id,
            role_id=q1.role_id,
            experience_level="fresher",
            tech_stack=["Java", "Spring Boot", "PostgreSQL", "React", "RESTful API"],
            language="vi",
            target_difficulty=2,
            estimated_duration_minutes=20,
            is_curated=True,
            is_active=True,
            practice_count=2450,
            avg_score=Decimal("82.5"),
            pass_rate=Decimal("78.0"),
        )
        set2 = QuestionSet(
            title="Bộ đề Frontend React / Next.js - Senior (Web Vitals & Performance)",
            description="Bộ câu hỏi chuyên sâu kiểm tra năng lực tối ưu hóa hiệu năng LCP/INP/CLS, kiến trúc Server Components, quản lý state phức tạp và kỹ năng Lead nhóm.",
            domain_id=q1.domain_id,
            role_id=questions[2].role_id if len(questions) > 2 else q1.role_id,
            experience_level="senior",
            tech_stack=["React", "Next.js", "TypeScript", "Tailwind CSS", "Web Vitals"],
            language="vi",
            target_difficulty=4,
            estimated_duration_minutes=25,
            is_curated=True,
            is_active=True,
            practice_count=1820,
            avg_score=Decimal("88.0"),
            pass_rate=Decimal("82.5"),
        )
        set3 = QuestionSet(
            title="Bộ đề DevOps & Hạ Tầng Cloud - Mid/Senior (CI/CD, Docker & K8s)",
            description="Khung câu hỏi kiểm tra kỹ năng tự động hóa hạ tầng, xử lý sự cố nghẽn pipeline, containerization và chiến lược triển khai không downtime.",
            domain_id=q1.domain_id,
            role_id=questions[4].role_id if len(questions) > 4 else q1.role_id,
            experience_level="mid",
            tech_stack=["Docker", "Kubernetes", "GitLab CI", "AWS", "Prometheus"],
            language="vi",
            target_difficulty=3,
            estimated_duration_minutes=20,
            is_curated=True,
            is_active=True,
            practice_count=1150,
            avg_score=Decimal("79.5"),
            pass_rate=Decimal("71.0"),
        )
        session.add_all([set1, set2, set3])
        session.commit()

        # Link QuestionSetItems
        q_ids = [q.question_id for q in questions[:5]]
        if len(q_ids) >= 3:
            # Set 1 items
            session.add_all([
                QuestionSetItem(set_id=set1.set_id, question_id=q_ids[0], order_index=1),
                QuestionSetItem(set_id=set1.set_id, question_id=q_ids[1], order_index=2),
                QuestionSetItem(set_id=set1.set_id, question_id=q_ids[2], order_index=3),
            ])
            # Set 2 items
            session.add_all([
                QuestionSetItem(set_id=set2.set_id, question_id=q_ids[2], order_index=1),
                QuestionSetItem(set_id=set2.set_id, question_id=q_ids[3], order_index=2),
                QuestionSetItem(set_id=set2.set_id, question_id=q_ids[0], order_index=3),
            ])
            # Set 3 items
            if len(q_ids) >= 5:
                session.add_all([
                    QuestionSetItem(set_id=set3.set_id, question_id=q_ids[4], order_index=1),
                    QuestionSetItem(set_id=set3.set_id, question_id=q_ids[0], order_index=2),
                    QuestionSetItem(set_id=set3.set_id, question_id=q_ids[1], order_index=3),
                ])
        session.commit()
    session.commit()
