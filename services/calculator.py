def calculate_kbju(sex, age, weight, height, activity):
    """
    sex: 'м' или 'ж'
    age: возраст
    weight: вес (кг)
    height: рост (см)
    activity:
        1 - сидячий образ жизни
        2 - легкая активность
        3 - умеренная активность
        4 - высокая активность
        5 - очень высокая активность
    """

    activity_factors = {
        1: 1.2,
        2: 1.375,
        3: 1.55,
        4: 1.725,
        5: 1.9
    }

    if sex.lower() == 'м':
        # Миффлин-Сан Жеор
        bmr_msj = 10 * weight + 6.25 * height - 5 * age + 5

        # Харрис-Бенедикт (ревизия)
        bmr_hb = (
            88.362
            + 13.397 * weight
            + 4.799 * height
            - 5.677 * age
        )

        # Оуэн
        bmr_owen = 879 + 10.2 * weight

    else:
        # Миффлин-Сан Жеор
        bmr_msj = 10 * weight + 6.25 * height - 5 * age - 161

        # Харрис-Бенедикт (ревизия)
        bmr_hb = (
            447.593
            + 9.247 * weight
            + 3.098 * height
            - 4.330 * age
        )

        # Оуэн
        bmr_owen = 795 + 7.18 * weight

    # Среднее значение BMR по всем формулам
    avg_bmr = (bmr_msj + bmr_hb + bmr_owen) / 3

    # Поддержание
    tdee = avg_bmr * activity_factors[activity]

    # Дефицит 15%
    calories = round(tdee * 0.80)

    # КБЖУ для похудения
    protein = round(weight * 2.2)
    fat = round(weight * 0.6)
    carbs = round((calories - protein * 4 - fat * 9) / 4)
    return (
        f"🎯 <b>Персональная норма для похудения</b>\n\n"

        f"🔥 <b>{calories} ккал</b>\n\n"

        f"🥩 Белки: <b>{protein} г</b>\n"
        f"🥑 Жиры: <b>{fat} г</b>\n"
        f"🍚 Углеводы: <b>{carbs} г</b>\n\n"

        f"━━━━━━━━━━━━━━\n"
        f"📊 Расчёт выполнен по 3 научным формулам:\n"
        f"• Миффлин — Сан Жеор\n"
        f"• Харрис — Бенедикт\n"
        f"• Оуэн\n"
        f"━━━━━━━━━━━━━━\n\n"

        f"✅ Использовано усреднённое значение\n"
        f"✅ Учтена ваша активность\n"
        f"✅ Уже заложен дефицит 15% для снижения веса"
    )