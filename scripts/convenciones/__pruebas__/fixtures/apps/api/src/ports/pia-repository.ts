export interface PiaRepository {
  buscar(id: string): Promise<unknown>;
}
