import asyncio
import html
import logging
import random
from datetime import datetime, timedelta

import aiohttp
import discord
import pytz
from discord import app_commands
from discord.ext import commands, tasks

from .quiz_logic import evaluate_schedule
from .util import (
    QUESTIONS_PATH,
    QUIZ_DATA_PATH,
    USED_QUESTIONS_PATH,
    load_json,
    save_json,
)

logger = logging.getLogger(__name__)

API_TIMEOUT = aiohttp.ClientTimeout(total=15)
USER_AGENT = "XEDB-Discord-Bot/1.0"


class QuizView(discord.ui.View):
    def __init__(self, question: str, choices: list[str], correct_index: int, quiz_callback):
        super().__init__(timeout=1800)
        self.question = question
        self.choices = choices
        self.correct_index = correct_index
        self.quiz_callback = quiz_callback
        self.answered_users = {}

        for i, choice in enumerate(choices):
            button = discord.ui.Button(label=choice, style=discord.ButtonStyle.primary, custom_id=f"choice_{i}")
            button.callback = self.create_response_callback(i)
            self.add_item(button)

    def create_response_callback(self, idx: int):
        async def response_callback(interaction: discord.Interaction):
            await self.handle_response(interaction, idx)

        return response_callback

    async def handle_response(self, interaction: discord.Interaction, chosen_index: int):
        if interaction.user.id in self.answered_users:
            await interaction.response.send_message("You have already answered this question!", ephemeral=True, delete_after=5)
            return

        self.answered_users[interaction.user.id] = chosen_index
        correct = chosen_index == self.correct_index
        await self.quiz_callback(interaction, correct, self.choices[self.correct_index])


class Quiz(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.data: dict = load_json(QUIZ_DATA_PATH)
        self.questions: dict[str, list] = load_json(QUESTIONS_PATH)
        self.used_questions: dict[str, list] = load_json(USED_QUESTIONS_PATH)
        self.category_mapping = {}
        self._last_start_attempt = None

        if not self.data:
            self.data = {
                "current_quiz": {},
                "points": {},
                "quiz_time": "06:00",
                "reveal_time": "18:00",
                "quiz_channel_id": None,
                "quiz_started": False,
                "quiz_finished_today": False,
                "last_quiz_date": None,
                "enabled_categories": ["General Knowledge"],
                "session_token": None,
            }
            try:
                save_json(QUIZ_DATA_PATH, self.data)
            except OSError:
                logger.exception("Failed to save initial quiz data")
        else:
            if self.data.get("quiz_started") and not self.data.get("current_quiz"):
                self.data["quiz_started"] = False
                try:
                    save_json(QUIZ_DATA_PATH, self.data)
                except OSError:
                    logger.exception("Failed to save corrected quiz data")

    async def cog_load(self):
        self.check_quiz_time.start()

    def cog_unload(self):
        self.check_quiz_time.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        try:
            await self.build_category_mapping()
        except Exception:
            logger.exception("Error in QuizCog on_ready")

    async def before_loop(self):
        await self.client.wait_until_ready()

    @tasks.loop(minutes=1)
    async def check_quiz_time(self):
        try:
            arizona_tz = pytz.timezone("US/Arizona")
            now = datetime.now(arizona_tz)

            action = evaluate_schedule(
                now,
                self.data.get("quiz_time", "06:00"),
                self.data.get("reveal_time", "18:00"),
                self.data.get("last_quiz_date", ""),
                self.data.get("quiz_started", False),
                self.data.get("quiz_finished_today", False),
            )

            if action == "reset":
                self.data["quiz_started"] = False
                self.data["quiz_finished_today"] = False
                self.data["current_quiz"] = {}
                self.data["last_quiz_date"] = now.date().isoformat()
                save_json(QUIZ_DATA_PATH, self.data)
                logger.info("Daily quiz state reset for %s", self.data["last_quiz_date"])

            elif action == "start":
                if self._last_start_attempt is None or (now - self._last_start_attempt) >= timedelta(minutes=10):
                    self._last_start_attempt = now
                    success = await self.start_quiz()
                    if success:
                        logger.info("Daily quiz posted")
                    else:
                        logger.warning("Failed to start quiz: %s", self.get_failure_reason())
                        reveal_time = datetime.strptime(self.data.get("reveal_time", "18:00"), "%H:%M").time()
                        reveal_time_today = now.replace(hour=reveal_time.hour, minute=reveal_time.minute, second=0, microsecond=0)
                        if now >= reveal_time_today:
                            self.data["quiz_finished_today"] = True
                            save_json(QUIZ_DATA_PATH, self.data)
                            logger.warning("Giving up on today's quiz after reveal time")
                else:
                    logger.debug("start_quiz attempt is on cooldown")

            elif action == "reveal":
                await self.reveal_answers()
                self.data["quiz_started"] = False
                self.data["quiz_finished_today"] = True
                self.data["current_quiz"] = {}
                save_json(QUIZ_DATA_PATH, self.data)
                logger.info("Daily quiz revealed")

        except Exception:
            logger.exception("Critical error in check_quiz_time")
            self.data["quiz_started"] = False
            self.data["quiz_finished_today"] = False
            save_json(QUIZ_DATA_PATH, self.data)

    async def build_category_mapping(self) -> None:
        url = "https://opentdb.com/api_category.php"
        headers = {"User-Agent": USER_AGENT}
        try:
            async with aiohttp.ClientSession(timeout=API_TIMEOUT, headers=headers) as session, session.get(url) as response:
                response.raise_for_status()
                data = await response.json()
            self.category_mapping = {category["name"]: category["id"] for category in data.get("trivia_categories", [])}
            logger.info("Fetched %s quiz categories from OpenTDB", len(self.category_mapping))
        except Exception as e:
            logger.warning("Error fetching categories: %s", e)
            self.category_mapping = {}

    async def get_session_token(self) -> str:
        url = "https://opentdb.com/api_token.php?command=request"
        headers = {"User-Agent": USER_AGENT}
        async with aiohttp.ClientSession(timeout=API_TIMEOUT, headers=headers) as session, session.get(url) as response:
            response.raise_for_status()
            data = await response.json()
            if data.get("response_code") == 0:
                return data["token"]
            raise RuntimeError("Failed to retrieve session token")

    async def reset_session_token(self, token: str) -> str:
        url = f"https://opentdb.com/api_token.php?command=reset&token={token}"
        headers = {"User-Agent": USER_AGENT}
        async with aiohttp.ClientSession(timeout=API_TIMEOUT, headers=headers) as session, session.get(url) as response:
            response.raise_for_status()
            data = await response.json()
            if data.get("response_code") == 0:
                return data["token"]
            raise RuntimeError("Failed to reset token")

    async def fetch_questions_from_api(self) -> bool:
        if not self.data.get("session_token"):
            try:
                self.data["session_token"] = await self.get_session_token()
                save_json(QUIZ_DATA_PATH, self.data)
            except Exception as e:
                logger.warning("Error getting session token: %s", e)
                return False

        headers = {"User-Agent": USER_AGENT}
        url = "https://opentdb.com/api.php"
        params = {"amount": 50, "token": self.data["session_token"]}

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                async with (
                    aiohttp.ClientSession(timeout=API_TIMEOUT, headers=headers) as session,
                    session.get(url, params=params) as response,
                ):
                    response.raise_for_status()
                    data = await response.json()
            except asyncio.TimeoutError:
                if attempt < max_attempts:
                    logger.warning("OpenTDB request timed out (attempt %s/%s); retrying", attempt, max_attempts)
                    await asyncio.sleep(2**attempt)
                    continue
                logger.exception("OpenTDB request timed out after %s attempts", max_attempts)
                return False
            except (aiohttp.ClientError, ValueError) as e:
                if attempt < max_attempts:
                    logger.warning("Transient OpenTDB error on attempt %s/%s: %s", attempt, max_attempts, e)
                    await asyncio.sleep(2**attempt)
                    continue
                logger.exception("OpenTDB request failed after %s attempts", max_attempts)
                return False

            response_code = data.get("response_code")
            if response_code == 1:
                logger.warning("OpenTDB returned no results for this token")
                return False
            if response_code in (3, 4):
                try:
                    if response_code == 3:
                        self.data["session_token"] = await self.get_session_token()
                        logger.info("OpenTDB token expired; requested a new one")
                    else:
                        self.data["session_token"] = await self.reset_session_token(self.data["session_token"])
                        logger.info("OpenTDB token exhausted; reset it")
                    save_json(QUIZ_DATA_PATH, self.data)
                    params["token"] = self.data["session_token"]
                except Exception as e:
                    logger.warning("Failed to refresh OpenTDB token: %s", e)
                    return False
                if attempt < max_attempts:
                    continue
                return False
            if response_code != 0:
                logger.warning("Unknown OpenTDB response code: %s", response_code)
                return False

            raw_questions = data.get("results", [])
            if not raw_questions:
                logger.warning("OpenTDB returned an empty results list")
                return False

            enabled_categories = self.data.get("enabled_categories", ["General Knowledge"])
            new_questions = []

            for q in raw_questions:
                category = html.unescape(q["category"])
                if category not in enabled_categories:
                    continue

                question_text = html.unescape(q["question"])
                correct_answer = html.unescape(q["correct_answer"])
                incorrect_answers = [html.unescape(a) for a in q["incorrect_answers"]]

                is_duplicate = False
                for used_q in self.used_questions.get(category, []):
                    if used_q["question"] == question_text:
                        is_duplicate = True
                        break
                if is_duplicate:
                    continue

                choices = list(dict.fromkeys([*incorrect_answers, correct_answer]))
                random.shuffle(choices)
                correct_index = choices.index(correct_answer)

                new_questions.append(
                    (
                        category,
                        {
                            "question": question_text,
                            "choices": choices,
                            "correct_index": correct_index,
                            "category": category,
                        },
                    )
                )

            for category, question in new_questions:
                if category not in self.questions:
                    self.questions[category] = []
                self.questions[category].append(question)

            if new_questions:
                save_json(QUESTIONS_PATH, self.questions)
            logger.info("Added %s new questions from OpenTDB", len(new_questions))
            return len(new_questions) > 0

        return False

    def get_random_question(self):
        enabled_categories = self.data.get("enabled_categories", [])
        available_categories = [cat for cat in enabled_categories if self.questions.get(cat)]

        if not available_categories:
            return None, None

        category = random.choice(available_categories)
        if not self.questions[category]:
            return None, None

        question = random.choice(self.questions[category])
        return category, question

    async def start_quiz(self) -> bool:
        if self.data.get("quiz_started") and self.data.get("current_quiz"):
            logger.info("Quiz already running; ignoring duplicate start")
            return True

        channel_id = self.data.get("quiz_channel_id")
        if not channel_id:
            return False

        channel = self.client.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return False

        try:
            enabled_categories = self.data.get("enabled_categories", [])
            total_questions = sum(len(self.questions.get(cat, [])) for cat in enabled_categories)

            if total_questions < 5:
                logger.info("Low on questions; fetching from API")
                success = await self.fetch_questions_from_api()
                if not success and total_questions == 0:
                    return False

            category, question = self.get_random_question()
            if not question:
                return False

            new_quiz = {
                "answers": {},
                "revealed": False,
                "question": question["question"],
                "choices": question["choices"],
                "correct_index": question["correct_index"],
                "category": category,
            }

            view = QuizView(
                question["question"],
                question["choices"],
                question["correct_index"],
                self.handle_quiz_callback,
            )
            await channel.send("🎯 **Daily Quiz Time!**\n" + question["question"], view=view)

            self.data["current_quiz"] = new_quiz
            self.data["quiz_started"] = True
            save_json(QUIZ_DATA_PATH, self.data)

            self.move_question_to_used(question, category)
            return True

        except Exception:
            logger.exception("CRITICAL FAILURE in start_quiz")
            self.data["current_quiz"] = {}
            self.data["quiz_started"] = False
            save_json(QUIZ_DATA_PATH, self.data)
            return False

    def move_question_to_used(self, question: dict, category: str):
        try:
            if category in self.questions and question in self.questions[category]:
                self.questions[category].remove(question)

            if category not in self.used_questions:
                self.used_questions[category] = []
            if question not in self.used_questions[category]:
                self.used_questions[category].append(question)

            save_json(QUESTIONS_PATH, self.questions)
            save_json(USED_QUESTIONS_PATH, self.used_questions)
        except Exception:
            logger.exception("Error moving question to used")

    async def handle_quiz_callback(self, interaction: discord.Interaction, correct: bool, correct_answer: str):
        current_quiz = self.data.get("current_quiz")
        if not current_quiz or not isinstance(current_quiz, dict) or "answers" not in current_quiz or "correct_index" not in current_quiz:
            await interaction.response.send_message("This quiz is no longer active.", ephemeral=True)
            return

        user_id = str(interaction.user.id)
        current_quiz["answers"][user_id] = {
            "correct": correct,
            "timestamp": datetime.now().isoformat(),
        }

        if correct:
            self.data["points"][user_id] = self.data["points"].get(user_id, 0) + 1

        save_json(QUIZ_DATA_PATH, self.data)
        await interaction.response.send_message(
            "✅ Correct!" if correct else f"❌ Wrong! The correct answer is: {correct_answer}",
            ephemeral=True,
            delete_after=60,
        )

    async def reveal_answers(self):
        try:
            current_quiz = self.data.get("current_quiz")
            if not current_quiz or not self.data.get("quiz_channel_id"):
                return

            channel = self.client.get_channel(self.data["quiz_channel_id"])
            if not channel:
                return

            correct_answer = current_quiz["choices"][current_quiz["correct_index"]]
            correct_users = [user_id for user_id, data in current_quiz.get("answers", {}).items() if data.get("correct")]

            await channel.send(
                f"📊 **Quiz Results**\n"
                f"Question: {current_quiz['question']}\n"
                f"Correct Answer: {correct_answer}\n"
                f"Number of correct answers: {len(correct_users)}\n"
                "\nCongratulations to everyone who got it right! 🎉"
            )
        except Exception:
            logger.exception("Failed to reveal quiz answers")

    def get_failure_reason(self) -> str:
        if not self.data.get("quiz_channel_id"):
            return "• No quiz channel set\nUse `/set_quiz_channel` first"

        channel = self.client.get_channel(self.data["quiz_channel_id"])
        if not channel:
            return "• Invalid channel ID\nRe-set with `/set_quiz_channel`"

        if channel and not channel.permissions_for(channel.guild.me).send_messages:
            return "• Missing Send Messages permission\nCheck channel permissions"

        enabled_categories = self.data.get("enabled_categories", [])
        if not enabled_categories:
            return "• No enabled categories\nUse `/enable_category`"

        total_questions = sum(len(self.questions.get(cat, [])) for cat in enabled_categories)
        if total_questions == 0:
            return "• No questions in enabled categories\nAdd questions or reset with `/reset_questions`"

        return "• Unknown error\nCheck console logs"

    @app_commands.command(name="set_quiz_channel", description="Set the channel for daily quizzes")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def set_quiz_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if channel.guild != interaction.guild:
            await interaction.response.send_message("The quiz channel must be in this server!", ephemeral=True, delete_after=5)
            return
        self.data["quiz_channel_id"] = channel.id
        save_json(QUIZ_DATA_PATH, self.data)
        await interaction.response.send_message(f"Quiz channel set to {channel.mention}", ephemeral=True, delete_after=5)

    @app_commands.command(name="set_quiz_time", description="Set the daily quiz start time (24-hour format, HH:MM)")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def set_quiz_time(self, interaction: discord.Interaction, start_time: str, end_time: str):
        try:
            start_time_obj = datetime.strptime(start_time, "%H:%M")
            end_time_obj = datetime.strptime(end_time, "%H:%M")
        except ValueError:
            await interaction.response.send_message(
                "Invalid time format. Please use HH:MM (24-hour format)", ephemeral=True, delete_after=10
            )
            return

        if not (start_time_obj < end_time_obj):
            await interaction.response.send_message("Start time must be before reveal time.", ephemeral=True, delete_after=10)
            return

        self.data["quiz_time"] = start_time_obj.strftime("%H:%M")
        self.data["reveal_time"] = end_time_obj.strftime("%H:%M")
        save_json(QUIZ_DATA_PATH, self.data)

        await interaction.response.send_message(
            f"Daily quiz time set to {start_time} and results reveal time set to {end_time}",
            ephemeral=True,
            delete_after=10,
        )

    @app_commands.command(name="start_quiz", description="start the daily quiz")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def start_quiz_command(self, interaction: discord.Interaction):
        if self.data.get("quiz_started") and self.data.get("current_quiz"):
            await interaction.response.send_message("A quiz is already running!", ephemeral=True, delete_after=5)
            return

        success = await self.start_quiz()
        if success:
            self.data["quiz_finished_today"] = False
            save_json(QUIZ_DATA_PATH, self.data)
            await interaction.response.send_message("✅ Quiz started successfully!", ephemeral=True, delete_after=5)
        else:
            failure_reason = self.get_failure_reason()
            await interaction.response.send_message(
                f"❌ Failed to start quiz:\n{failure_reason}",
                ephemeral=True,
                delete_after=15,
            )

    @app_commands.command(name="list_categories", description="List all available quiz categories")
    @app_commands.guild_only()
    async def list_categories(self, interaction: discord.Interaction):
        if not self.category_mapping:
            await self.build_category_mapping()

        enabled_categories = self.data.get("enabled_categories", [])
        category_counts = {}
        for category in self.questions:
            category_counts[category] = len(self.questions[category])

        embed = discord.Embed(title="Quiz Categories", color=discord.Color.blue())

        enabled_text = ""
        for category in enabled_categories:
            count = category_counts.get(category, 0)
            enabled_text += f"• {category} ({count} questions)\n"

        embed.add_field(
            name="📚 Enabled Categories",
            value=enabled_text if enabled_text else "No categories enabled",
            inline=False,
        )

        if self.category_mapping:
            available_text = ""
            for name in sorted(self.category_mapping):
                marker = "✅ " if name in enabled_categories else ""
                count = category_counts.get(name, 0)
                available_text += f"{marker}{name} ({count} questions)\n"
            embed.add_field(
                name="🌐 Available Categories",
                value=available_text if available_text else "None",
                inline=False,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="enable_category", description="Enable a quiz category")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def enable_category(self, interaction: discord.Interaction, category: str):
        if not self.category_mapping:
            await self.build_category_mapping()
            if not self.category_mapping:
                await interaction.response.send_message("Could not fetch categories from the API. Try again later.", ephemeral=True)
                return

        matching = next((name for name in self.category_mapping if name.lower() == category.lower()), None)
        if matching is None:
            await interaction.response.send_message(
                f"Category '{category}' not found. Use /list_categories to see available categories.",
                ephemeral=True,
            )
            return

        if "enabled_categories" not in self.data:
            self.data["enabled_categories"] = []

        if matching not in self.data["enabled_categories"]:
            self.data["enabled_categories"].append(matching)
            save_json(QUIZ_DATA_PATH, self.data)
            await interaction.response.send_message(f"Enabled category: {matching}", ephemeral=True)
        else:
            await interaction.response.send_message(f"Category {matching} is already enabled", ephemeral=True)

    @app_commands.command(name="quiz_status", description="Show current leaderboard and question status")
    @app_commands.guild_only()
    async def quiz_status(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Quiz Status", color=discord.Color.blue())

        points_data = self.data["points"]
        sorted_users = sorted(points_data.items(), key=lambda x: x[1], reverse=True)[:10]

        leaderboard = []
        for idx, (user_id, points) in enumerate(sorted_users, 1):
            user = interaction.guild.get_member(int(user_id))
            leaderboard.append(f"{idx}. {user.mention if user else 'Unknown User'} - {points} pts")

        embed.add_field(
            name="🏆 Leaderboard",
            value="\n".join(leaderboard) if leaderboard else "No points yet!",
            inline=False,
        )

        current_quiz = self.data.get("current_quiz", {})
        if current_quiz:
            question_status = [
                f"**Question:** {current_quiz.get('question', 'N/A')}",
                f"**Category:** {current_quiz.get('category', 'N/A')}",
            ]

            choices = current_quiz.get("choices", [])
            for i, choice in enumerate(choices):
                question_status.append(f"{chr(65 + i)}) {choice}")

            if current_quiz.get("revealed", False) and current_quiz.get("correct_index") is not None and choices:
                correct_answer = choices[current_quiz["correct_index"]]
                question_status.append(f"\n✅ **Correct Answer:** {correct_answer}")

            embed.add_field(
                name="📚 Current Question",
                value="\n".join(question_status),
                inline=False,
            )

            correct_users = []
            wrong_users = []

            for user_id, answer in current_quiz.get("answers", {}).items():
                user = interaction.guild.get_member(int(user_id))
                if user:
                    name = user.display_name
                    if answer["correct"]:
                        correct_users.append(name)
                    else:
                        wrong_users.append(name)

            embed.add_field(
                name="✅ Correct Answers",
                value="\n".join(correct_users) if correct_users else "No correct answers yet",
                inline=True,
            )

            embed.add_field(
                name="❌ Incorrect Answers",
                value="\n".join(wrong_users) if wrong_users else "No wrong answers yet",
                inline=True,
            )
        else:
            embed.add_field(
                name="📚 Current Question",
                value="No active quiz at the moment!",
                inline=False,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="points", description="Check your quiz points")
    @app_commands.guild_only()
    async def show_points(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        points = self.data["points"].get(user_id, 0)
        await interaction.response.send_message(f"🎉 You currently have **{points}** quiz points!", ephemeral=True)

    @app_commands.command(name="reset_questions", description="Reset all used questions back to active pool")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def reset_questions(self, interaction: discord.Interaction):
        for category in self.used_questions:
            if category not in self.questions:
                self.questions[category] = []
            self.questions[category].extend(self.used_questions[category])

        self.used_questions = {category: [] for category in self.used_questions}

        save_json(QUESTIONS_PATH, self.questions)
        save_json(USED_QUESTIONS_PATH, self.used_questions)

        await interaction.response.send_message("All questions have been reset!", ephemeral=True)

    @app_commands.command(name="force_reset_quiz", description="Emergency reset command")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def force_reset_quiz(self, interaction: discord.Interaction):
        self.data["quiz_started"] = False
        self.data["quiz_finished_today"] = False
        self.data["current_quiz"] = {}
        save_json(QUIZ_DATA_PATH, self.data)
        await interaction.response.send_message("✅ Quiz state forcibly reset", ephemeral=True)


async def setup(client):
    await client.add_cog(Quiz(client))
    logger.info("Quiz System Online")
