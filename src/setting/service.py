from fastapi import HTTPException, status
from sqlalchemy import select, insert, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.schemas import DataResponse
from src.setting.schemas import GetSettingResponse, UpdateSettingParam
from src.models import Setting


async def get_settings(
    session: AsyncSession,
) -> DataResponse[GetSettingResponse]:
    query = select(
        Setting.setting_id,
        Setting.is_auto_delete,
        Setting.is_auto_clean,
    )

    result = (await session.execute(query)).mappings().first()

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Setting not found",
        )

    return DataResponse[GetSettingResponse](
        data=result,
    )


async def update_settings(session: AsyncSession, setting_data: UpdateSettingParam):
    try:
        select_query = select(Setting)
        result = await session.execute(select_query)
        setting = result.first()

        if not setting:
            query = insert(Setting).values(
                {
                    "is_auto_delete": setting_data.is_auto_delete,
                    "is_auto_clean": setting_data.is_auto_clean,
                }
            )
        else:
            query = update(Setting).values(
                {
                    "is_auto_delete": setting_data.is_auto_delete,
                    "is_auto_clean": setting_data.is_auto_clean,
                }
            )
        await session.execute(query)
        await session.commit()

    except Exception as e:
        await session.rollback()
        raise e
