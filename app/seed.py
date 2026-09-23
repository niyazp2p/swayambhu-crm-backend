import asyncio
from sqlalchemy import select
from app.db.session import async_session_factory
from app.models.plant import Plant
from app.models.user import User, UserRole
from app.core.security import get_password_hash

# Default Seed Accounts Configuration
ACCOUNTS_DATA = [
    {
        "email": "admin@swayambhuinfo.com",
        "password": "Admin@123",
        "full_name": "Akansha Singh (Super Admin)",
        "role": UserRole.SUPER_ADMIN,
        "plant_scoped": False,
    },
    {
        "email": "manager@swayambhuinfo.com",
        "password": "Manager@123",
        "full_name": "Priyank Gupta (Plant Manager)",
        "role": UserRole.PLANT_MANAGER,
        "plant_scoped": True,
    },
    {
        "email": "hr@swayambhuinfo.com",
        "password": "Hr@123",
        "full_name": "HR Operations Officer",
        "role": UserRole.HR_OFFICER,
        "plant_scoped": True,
    },
    {
        "email": "operator@swayambhuinfo.com",
        "password": "Operator@123",
        "full_name": "Weighbridge Intake Operator",
        "role": UserRole.WEIGHBRIDGE_OPERATOR,
        "plant_scoped": True,
    },
    {
        "email": "logistics@swayambhuinfo.com",
        "password": "Logistics@123",
        "full_name": "Outward Logistics Officer",
        "role": UserRole.WEIGHBRIDGE_OPERATOR,
        "plant_scoped": True,
    },
]


async def seed_database() -> None:
    async with async_session_factory() as session:
        # 1. Ensure Default Facility Exists (Haridwar SIDCUL Complex)
        plant_stmt = select(Plant).where(Plant.code == "SIS-HRD-01")
        result = await session.execute(plant_stmt)
        default_plant = result.scalar_one_or_none()

        if not default_plant:
            default_plant = Plant(
                name="Haridwar SIDCUL Recycling Complex",
                code="SIS-HRD-01",
                address="Plot-5A2, Sector 3, IIE BHEL, SIDCUL, Haridwar, Uttarakhand - 249403",
                is_active=True,
            )
            session.add(default_plant)
            await session.flush()
            print(f"[+] Created primary plant: {default_plant.name} (Code: {default_plant.code})")
        else:
            print(f"[*] Found existing plant: {default_plant.name}")

        # 2. Seed Users
        for acc in ACCOUNTS_DATA:
            user_stmt = select(User).where(User.email == acc["email"])
            res = await session.execute(user_stmt)
            existing_user = res.scalar_one_or_none()

            plant_id = default_plant.id if acc["plant_scoped"] else None

            if not existing_user:
                new_user = User(
                    email=acc["email"],
                    hashed_password=get_password_hash(acc["password"]),
                    full_name=acc["full_name"],
                    role=acc["role"],
                    plant_id=plant_id,
                    is_active=True,
                )
                session.add(new_user)
                print(f"[+] Created user: {acc['email']} [{acc['role'].value}]")
            else:
                existing_user.hashed_password = get_password_hash(acc["password"])
                existing_user.full_name = acc["full_name"]
                existing_user.plant_id = plant_id
                existing_user.role = acc["role"]
                print(f"[*] Updated existing credentials for: {acc['email']}")

        await session.commit()
        print("\n Seeding completed successfully for @swayambhuinfo.com.")


if __name__ == "__main__":
    asyncio.run(seed_database())