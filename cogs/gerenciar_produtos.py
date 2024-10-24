import discord
from discord import app_commands
from discord.ext import commands
from motor.motor_asyncio import AsyncIOMotorClient

client = AsyncIOMotorClient("URL MONGODB")
db = client['vendas']
produtos_db = db['produtos']

# Cog de Gerenciamento
class Gerenciamento(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_produtos(self):
        produtos = await produtos_db.find().to_list(None)
        return [produto['nome'] for produto in produtos]

    @app_commands.command(name="gerenciar_produto", description="Gerencia produtos no banco de dados.")
    @app_commands.describe(
        funcao="Função a ser executada (Adicionar, Remover, Atualizar).",
        produto="Nome do produto a ser gerenciado.",
        nome="Novo nome do produto.",
        descricao="Nova descrição do produto.",
        imagem="URL da imagem do produto.",
        nome_opcao="Nome da opção a ser adicionada ou atualizada.",
        preco="Preço da opção a ser adicionada ou atualizada."
    )
    @app_commands.choices(
        funcao=[
            app_commands.Choice(name="Adicionar", value="adicionar"),
            app_commands.Choice(name="Remover", value="remover"),
            app_commands.Choice(name="Atualizar", value="atualizar")
        ]
    )
    async def gerenciar_produto(
        self,
        interaction: discord.Interaction,
        funcao: app_commands.Choice[str],
        produto: str,
        nome: str = None,
        descricao: str = None,
        imagem: str = None,
        nome_opcao: str = None,
        preco: float = None
    ):
        funcao = funcao.value

        if funcao not in ["adicionar", "remover", "atualizar"]:
            await interaction.response.send_message("Função inválida! Use 'Adicionar', 'Remover' ou 'Atualizar'.", ephemeral=True)
            return

        if funcao == "adicionar":
            produto_existente = await produtos_db.find_one({"nome": produto})
            if produto_existente:
                await interaction.response.send_message(f"Produto '{produto}' já existe!", ephemeral=True)
                return
            
            novo_produto = {
                "nome": nome if nome else produto,
                "descricao": descricao if descricao else "Sem descrição.",
                "imagem": imagem if imagem else None,
                "opcoes": {}
            }

            if nome_opcao and preco:
                novo_produto["opcoes"][nome_opcao] = {"preco": preco}

            await produtos_db.insert_one(novo_produto)
            await interaction.response.send_message(f"Produto '{produto}' adicionado com sucesso!", ephemeral=True)

        elif funcao == "remover":
            resultado = await produtos_db.delete_one({"nome": produto})
            if resultado.deleted_count:
                await interaction.response.send_message(f"Produto '{produto}' removido com sucesso!", ephemeral=True)
            else:
                await interaction.response.send_message(f"Produto '{produto}' não encontrado!", ephemeral=True)

        elif funcao == "atualizar":
            produto_existente = await produtos_db.find_one({"nome": produto})
            if not produto_existente:
                await interaction.response.send_message(f"Produto '{produto}' não encontrado!", ephemeral=True)
                return

            novos_valores = {}
            if nome:
                novos_valores["nome"] = nome
            if descricao:
                novos_valores["descricao"] = descricao
            if imagem:
                novos_valores["imagem"] = imagem

            if novos_valores:
                await produtos_db.update_one({"nome": produto}, {"$set": novos_valores})

            if nome_opcao and preco:
                await produtos_db.update_one(
                    {"nome": produto},
                    {"$set": {f"opcoes.{nome_opcao}": {"preco": preco}}}
                )

            await interaction.response.send_message(f"Produto '{produto}' atualizado com sucesso!", ephemeral=True)

    @gerenciar_produto.autocomplete('produto')
    async def autocomplete_produto(self, interaction: discord.Interaction, current: str):
        produtos = await self.get_produtos()
        return [
            app_commands.Choice(name=produto, value=produto)
            for produto in produtos if current.lower() in produto.lower()
        ]

async def setup(bot):
    await bot.add_cog(Gerenciamento(bot))