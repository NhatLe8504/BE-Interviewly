from __future__ import annotations

from typing import Any

from sqlalchemy import select

from ...application.auth.ports import PasswordHasherPort
from .models.catalog import (
    JobDomain,
    JobRole,
    QuestionBank,
    StarGuidanceTemplate,
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
    finally:
        session.close()
