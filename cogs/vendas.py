import discord
from discord import app_commands
from discord.ext import commands
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
import mercadopago
import asyncio
import base64
import io
from typing import Optional

mp = mercadopago.SDK("TOKEN MERCADO PAGO SDK")

client = AsyncIOMotorClient(" URL MONGODB")
db = client['vendas']
produtos_db = db['produtos']
pontos = db['pontos']

class ProdutoSelectView(discord.ui.View):
    def __init__(self, interaction: discord.Interaction, produto: dict, opcoes: dict, timeout: Optional[float] = None):
        super().__init__(timeout=timeout)
        self.interaction = interaction
        self.produto = produto
        self.opcoes = opcoes
        self.add_item(ProdutoSelect(produto, opcoes))

class ProdutoSelect(discord.ui.Select):
    def __init__(self, produto, opcoes):
        self.produto = produto
        self.opcoes = opcoes
        options = [
            discord.SelectOption(label=opcao, description=f"R$ {dados['preco']:.2f}", emoji='<:cherry:1293232336833613874>')
            for opcao, dados in opcoes.items()
        ]
        super().__init__(placeholder="Escolha uma opção...", options=options)

    async def callback(self, interaction: discord.Interaction):
        opcao_escolhida = self.values[0]
        preco = self.opcoes[opcao_escolhida]['preco']

        await interaction.response.send_message(
            f"Você escolheu **{self.produto['nome']} {opcao_escolhida}** no valor de **R${preco:.2f}**\nDeseja confirmar ou cancelar a compra?",
            view=ConfirmarCancelarView(self.produto, opcao_escolhida, preco, interaction.user.id))
        await interaction.message.delete()

class ConfirmarCancelarView(discord.ui.View):
    def __init__(self, produto, opcao, preco,comprador_id, timeout: Optional[float] = None):
        super().__init__(timeout=timeout)
        self.produto = produto
        self.opcao = opcao
        self.preco = preco
        self.comprador_id = comprador_id
        self.add_item(ConfirmarCompraButton(self.produto, self.opcao, self.preco, self.comprador_id))
        self.add_item(CancelarCompraButton())

class ConfirmarCompraButton(discord.ui.Button):
    def __init__(self, produto, opcao, preco, comprador_id):
        super().__init__(label="Confirmar Compra", style=discord.ButtonStyle.success)
        self.produto = produto
        self.opcao = opcao
        self.preco = preco
        self.comprador_id = comprador_id

    async def callback(self, interaction: discord.Interaction):
        pagamento = {
            "transaction_amount": float(self.preco),
            "description": "Loja",
            "payment_method_id": "pix",
            "payer": {"email": "teste@example.com"}
        }
        pagamento_resposta = mp.payment().create(pagamento)
        qr_code_url = pagamento_resposta['response']['point_of_interaction']['transaction_data']['qr_code']
        qr_code_imagem_url = pagamento_resposta['response']['point_of_interaction']['transaction_data']['qr_code_base64']
        image_data = base64.b64decode(qr_code_imagem_url)
        image_bytes = io.BytesIO(image_data)

        await interaction.response.send_message(
            f"**Detalhes da compra**\nProduto: {self.produto['nome']}\nOpção: {self.opcao}\nValor: **R${self.preco:.2f}**\n\nPague o QR Code abaixo:\n\n{qr_code_url}",
            file=discord.File(image_bytes, filename="qr_code.png"))
        await interaction.message.delete()


        payment_id = pagamento_resposta['response']['id']
        channel = interaction.channel

        while True:
            pagamento_status = mp.payment().get(payment_id)
            status = pagamento_status['response']['status']

            if status == 'approved':
                await db['pontos'].update_one(
                {"user_id": self.comprador_id}, 
                {"$inc": {"pontos": int(self.preco * 0.1)}}, upsert=True)
                usuario = interaction.guild.get_member(self.comprador_id)
                await channel.send(f'{usuario.mention} Ganhou {int(self.preco * 0.1)} pontos pela compra, acesse <#1294823807646695435> para utilizar seus pontos.')

                embed = discord.Embed(title="Venda Concluída", description="Detalhes da venda realizada", color=discord.Color.pink())
                embed.add_field(name="Comprador", value=usuario.name, inline=False)
                embed.add_field(name="Data", value=datetime.utcnow().strftime("%d/%m/%Y"), inline=False)
                embed.add_field(name="Produto", value=self.produto['nome'], inline=False)
                embed.add_field(name="Valor Pago", value=f"R$ {self.preco:.2f}", inline=False)
                embed.set_footer(text="Venda concluída com sucesso!")
                chat_especifico = interaction.guild.get_channel(1290789965159989328)
                await chat_especifico.send(embed=embed)
                break

            await asyncio.sleep(10)

class CancelarCompraButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Cancelar Compra", style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"Compra cancelada! Caso queira fechar o chat, clique no botão 'Encerrar Chat', caso queira selecionar outra opção, é só escolher e concluir a compra !", 
            ephemeral=True)
        await interaction.message.delete()

class VendaButtonView(discord.ui.View):
    def __init__(self, timeout: Optional[float] = None):
        super().__init__(timeout=timeout)
        self.add_item(EncerrarChatButton())

class EncerrarChatButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Encerrar Chat", style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction):
        await interaction.channel.delete()

class Vendas(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_produtos(self):
        produtos = await produtos_db.find().to_list(None)
        return produtos

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'{__name__} foi carregado')

    @app_commands.command(name="menu", description="Envia o menu de vendas")
    @app_commands.checks.has_permissions(administrator=True)
    async def vender(self, interaction: discord.Interaction):
        channel = interaction.channel
        produtos = await self.get_produtos()

        embed = discord.Embed(
            title="Ticket de Compra",
            description="Selecione um produto",
            color=0xff0d35
        )

        options = [
            discord.SelectOption(label=produto['nome'], description=produto['descricao'], emoji='<:cherry:1293232336833613874>')
            for produto in produtos
        ]

        select = discord.ui.Select(
            placeholder="Escolha um produto...",
            options=options
        )

        async def select_callback(interaction_select: discord.Interaction):
            await self.criar_chat(interaction, select.values[0], interaction_select)

        select.callback = select_callback

        view = discord.ui.View(timeout=None)
        view.add_item(select)

        await channel.send(embed=embed, view=view)
        await channel.send('https://cdn.discordapp.com/attachments/1249905962580578304/1257778221722763326/7.png?ex=67062f00&is=6704dd80&hm=be79b44af6adf5f7b43335dfced3501a5d8dea94131b6812d826c9f2636b2f20&')

    async def criar_chat(self, interaction: discord.Interaction, produto_nome, interaction_select: discord.Interaction):
        guild = interaction.guild
        categoria = discord.utils.get(guild.categories, id=1290775451559526491)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction_select.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True)
        }
        existing_channel = discord.utils.get(guild.text_channels, name=f"compras-{interaction.user.name}")
        if existing_channel:
            await interaction_select.response.send_message(f'Você já tem um canal aberto {existing_channel.mention}', ephemeral=True)
        else:
            channel = await guild.create_text_channel(
                f"compras-{interaction_select.user.name}",
                category=categoria,
                overwrites=overwrites)

            produto_info = await produtos_db.find_one({'nome': produto_nome})
            if produto_info:
                descricao = produto_info['descricao']
                imagem = produto_info.get('imagem', None)
                opcoes = produto_info['opcoes']

                embed = discord.Embed(
                    title=f"Você escolheu {produto_nome}",
                    description=descricao,
                    color=discord.Color.blue()
                )
                if imagem:
                    embed.set_image(url=imagem)

                await channel.send(f'{interaction_select.user.mention}', embed=embed, view=ProdutoSelectView(interaction_select, produto_info, opcoes))
                await channel.send('https://cdn.discordapp.com/attachments/1249905962580578304/1257778221722763326/7.png?ex=67062f00&is=6704dd80&hm=be79b44af6adf5f7b43335dfced3501a5d8dea94131b6812d826c9f2636b2f20&')

                await channel.send(view=VendaButtonView())
                await interaction_select.response.send_message(f"Seu ticket foi criado: {channel.mention}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Vendas(bot))
