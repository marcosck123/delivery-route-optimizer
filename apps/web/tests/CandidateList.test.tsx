import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import CandidateList from "@/components/CandidateList";
import type { GeocodeCandidate } from "@/lib/types";

const CANDIDATES: GeocodeCandidate[] = [
  {
    latitude: -12.74,
    longitude: -60.14,
    formatted_address: "Rua Sete, 10 - Centro, Vilhena - RO",
    distance_m: 0,
  },
  {
    latitude: -12.79,
    longitude: -60.19,
    formatted_address: "Rua Sete, 10 - Jardim Eldorado, Vilhena - RO",
    distance_m: 820,
  },
];

describe("CandidateList", () => {
  it("não aparece quando só há uma opção", () => {
    const { container } = render(
      <CandidateList candidates={[CANDIDATES[0]]} onSelect={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("mostra o endereço formatado do Google de cada opção", () => {
    render(<CandidateList candidates={CANDIDATES} onSelect={vi.fn()} />);

    expect(screen.getByText("Qual desses é o endereço certo?")).toBeInTheDocument();
    expect(
      screen.getByText(/Rua Sete, 10 - Jardim Eldorado/),
    ).toBeInTheDocument();
  });

  it("mostra a distância até o pin atual", () => {
    render(<CandidateList candidates={CANDIDATES} onSelect={vi.fn()} />);

    expect(screen.getByText("no ponto atual")).toBeInTheDocument();
    expect(screen.getByText("a 820 m do pin atual")).toBeInTheDocument();
  });

  it("formata distâncias longas em quilômetros", () => {
    render(
      <CandidateList
        candidates={[
          CANDIDATES[0],
          { ...CANDIDATES[1], distance_m: 2400 },
        ]}
        onSelect={vi.fn()}
      />,
    );

    expect(screen.getByText("a 2,4 km do pin atual")).toBeInTheDocument();
  });

  it("devolve a opção escolhida", async () => {
    const onSelect = vi.fn();
    render(<CandidateList candidates={CANDIDATES} onSelect={onSelect} />);

    await userEvent.click(screen.getByText(/Jardim Eldorado/));

    expect(onSelect).toHaveBeenCalledWith(CANDIDATES[1]);
  });

  it("destaca a opção que está selecionada", () => {
    render(
      <CandidateList
        candidates={CANDIDATES}
        selected={{ latitude: -12.79, longitude: -60.19 }}
        onSelect={vi.fn()}
      />,
    );

    const selected = screen.getByText(/Jardim Eldorado/).closest("button");
    expect(selected?.className).toContain("border-blue-600");
  });

  it("cai para as coordenadas quando o Google não devolveu o texto", () => {
    render(
      <CandidateList
        candidates={[
          { latitude: -12.74, longitude: -60.14 },
          { latitude: -12.79, longitude: -60.19 },
        ]}
        onSelect={vi.fn()}
      />,
    );

    expect(screen.getByText(/-12\.74000, -60\.14000/)).toBeInTheDocument();
  });

  it("orienta a arrastar o pin se nenhuma opção servir", () => {
    render(<CandidateList candidates={CANDIDATES} onSelect={vi.fn()} />);

    expect(
      screen.getByText("Se nenhum estiver certo, arraste o pin no mapa."),
    ).toBeInTheDocument();
  });
});
