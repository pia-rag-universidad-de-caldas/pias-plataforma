import { Controller, Get, Injectable, Module } from "@nestjs/common";

@Injectable()
export class PiasService {}

@Controller("pias")
export class PiasController {
  @Get()
  listar() {
    return [];
  }
}

@Module({})
export class PiasModule {}
