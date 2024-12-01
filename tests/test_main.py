import unittest
from unittest.mock import AsyncMock, patch
from main import UtilityBot

class TestUtilityBot(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = UtilityBot()

    @patch('main.UtilityBot.setup_hook')
    async def test_setup_hook(self, mock_setup_hook):
        mock_setup_hook.return_value = None
        await self.bot.setup_hook()
        mock_setup_hook.assert_called_once()

    @patch('main.UtilityBot.on_ready')
    async def test_on_ready(self, mock_on_ready):
        mock_on_ready.return_value = None
        await self.bot.on_ready()
        mock_on_ready.assert_called_once()

    async def asyncTearDown(self):
        await self.bot.close()

if __name__ == '__main__':
    unittest.main()
