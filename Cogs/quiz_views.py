"""Daily quiz answer buttons."""

import asyncio

import discord


class QuizView(discord.ui.View):
    def __init__(self, question: str, choices: list[str], correct_index: int, quiz_callback):
        super().__init__(timeout=1800)
        self.question = question
        self.choices = choices
        self.correct_index = correct_index
        self.quiz_callback = quiz_callback
        self.answered_users = {}
        self._answer_lock = asyncio.Lock()

        for i, choice in enumerate(choices):
            button = discord.ui.Button(label=choice, style=discord.ButtonStyle.primary, custom_id=f"choice_{i}")
            button.callback = self.create_response_callback(i)
            self.add_item(button)

    def create_response_callback(self, idx: int):
        async def response_callback(interaction: discord.Interaction):
            await self.handle_response(interaction, idx)

        return response_callback

    async def handle_response(self, interaction: discord.Interaction, chosen_index: int):
        async with self._answer_lock:
            if interaction.user.id in self.answered_users:
                await interaction.response.send_message("You have already answered this question!", ephemeral=True, delete_after=5)
                return
            self.answered_users[interaction.user.id] = chosen_index
        correct = chosen_index == self.correct_index
        await self.quiz_callback(interaction, correct, self.choices[self.correct_index])

